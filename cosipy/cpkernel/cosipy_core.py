import numpy as np
import pandas as pd

from constants import mult_factor_RRR, densification_method, ice_density, water_density, \
                      minimum_snowfall, zero_temperature, lat_heat_sublimation, \
                      lat_heat_melting, lat_heat_vaporize, center_snow_transfer_function, \
                      spread_snow_transfer_function, constant_density, albedo_ice, make_icestupa, \
                        roughness_ice, z, temperature_threshold_precipitation, penetrating_method
from config import force_use_TP, force_use_N, stake_evaluation, cld, \
drone_evaluation,thermistor_evaluation, thermalcam_evaluation, full_field, WRF_X_CSPY

from cosipy.modules.albedo import updateAlbedo
from cosipy.modules.heatEquation import solveHeatEquation
from cosipy.modules.penetratingRadiation import penetrating_radiation
from cosipy.modules.percolation import percolation
from cosipy.modules.refreezing import refreezing
from cosipy.modules.roughness import updateRoughness
from cosipy.modules.densification import densification
from cosipy.modules.evaluation import evaluate
from cosipy.modules.surfaceTemperature import update_surface_temperature, get_subT
from cosipy.modules.shape import update_cone
from cosipy.modules.emissivity import updateEmissionCoeff

from cosipy.cpkernel.init import init_snowpack, load_snowpack
from cosipy.cpkernel.io import IOClass


def cosipy_core(DATA, indY, indX, GRID_RESTART=None, stake_names=None, stake_data=None):
    """ Cosipy core function, which perform the calculations on one core.

    Params
    ======
    DATA: xarray.Dataset
      xarray dataset which contain one grid point
    indY: 
    indX:
    GRID_RESTART : boolean, optional
      If restart is given, no inital profile is created
    stake_name : boolean, optional
      stake names      
    stake_data : boolean, optional
      stake data
    Returns
    ======
    Returns all calculated variables of one grid point

    """
    
    # Replace values from constants.py if coupled
    from constants import max_layers, dt, z	 #WTF python!
    if WRF_X_CSPY:
        dt = int(DATA.DT.values)
        max_layers = int(DATA.max_layers.values)
        z = float(DATA.ZLVL.values)

    # Local variables
    nt = len(DATA.time.values)         #accessing DATA is expensive 		
    _RRR = np.full(nt, np.nan)
    _RAIN = np.full(nt, np.nan)
    _DISF = np.full(nt, np.nan)
    _SNOWFALL = np.full(nt, np.nan)
    _LWin = np.full(nt, np.nan)
    _LWout = np.full(nt, np.nan)
    _H = np.full(nt, np.nan)
    _LE = np.full(nt, np.nan)
    _B = np.full(nt, np.nan)
    _QRR = np.full(nt, np.nan)
    _QFR = np.full(nt, np.nan)
    _MB = np.full(nt, np.nan)
    _surfMB = np.full(nt, np.nan)
    _MB = np.full(nt, np.nan)
    _Q = np.full(nt, np.nan)
    _SNOWHEIGHT = np.full(nt, np.nan)
    _TOTALHEIGHT = np.full(nt, np.nan)
    _TS = np.full(nt, np.nan)
    _ALBEDO = np.full(nt, np.nan)
    _SWNET = np.full(nt, np.nan)
    _ME = np.full(nt, np.nan)
    _FE = np.full(nt, np.nan)
    _ICE = np.full(nt, np.nan)
    _intMB = np.full(nt, np.nan)
    _EVAPORATION = np.full(nt, np.nan)
    _SUBLIMATION = np.full(nt, np.nan)
    _CONDENSATION = np.full(nt, np.nan)
    _DEPOSITION = np.full(nt, np.nan)
    _REFREEZE = np.full(nt, np.nan)
    _NLAYERS = np.full(nt, np.nan)
    _subM = np.full(nt, np.nan)
    _Z0 = np.full(nt, np.nan)
    _surfM = np.full(nt, np.nan)
    _MOL = np.full(nt, np.nan)
    _CONERAD = np.full(nt, np.nan)
    _CONEHEIGHT = np.full(nt, np.nan)
    _CONESLOPE = np.full(nt, np.nan)
    _CONEAREA = np.full(nt, np.nan)
    _CONEVOL = np.full(nt, np.nan)
    _RHO = np.full(nt, np.nan)
    _TBULK = np.full(nt, np.nan)

    _LAYER_HEIGHT = np.full((nt,max_layers), np.nan)
    _LAYER_RHO = np.full((nt,max_layers), np.nan)
    _LAYER_T = np.full((nt,max_layers), np.nan)
    _LAYER_LWC = np.full((nt,max_layers), np.nan)
    _LAYER_CC = np.full((nt,max_layers), np.nan)
    _LAYER_POROSITY = np.full((nt,max_layers), np.nan)
    _LAYER_ICE_FRACTION = np.full((nt,max_layers), np.nan)
    _LAYER_IRREDUCIBLE_WATER = np.full((nt,max_layers), np.nan)
    _LAYER_REFREEZE = np.full((nt,max_layers), np.nan)


    #--------------------------------------------
    # Initialize snowpack or load restart grid
    #--------------------------------------------
    if GRID_RESTART is None:
        GRID, r_cone, h_cone = init_snowpack(DATA)
        radf = r_cone
        s_cone = h_cone/r_cone
        A_cone = np.pi * r_cone * np.sqrt(r_cone**2 + h_cone**2)
        V_cone = 1/3 * np.pi * r_cone **2 * h_cone
    else:
        GRID = load_snowpack(GRID_RESTART)

    # Create the local output datasets if not coupled
    RESTART = None
    if not WRF_X_CSPY:
        IO = IOClass(DATA)
        RESTART = IO.create_local_restart_dataset()

    # hours since the last snowfall (albedo module)
    hours_since_snowfall = 0

    #--------------------------------------------
    # Get data from file
    #--------------------------------------------
    T2 = DATA.T2.values
    RH2 = DATA.RH2.values
    PRES = DATA.PRES.values
    G = DATA.G.values
    U2 = DATA.U2.values

    #--------------------------------------------
    # Checks for optional input variables
    #--------------------------------------------
    if ('SNOWFALL' in DATA) and ('RRR' in DATA):
        SNOWF = DATA.SNOWFALL.values * mult_factor_RRR
        RRR = DATA.RRR.values * mult_factor_RRR

    elif ('SNOWFALL' in DATA):
        SNOWF = DATA.SNOWFALL.values * mult_factor_RRR
        RRR = None
        RAIN = None

    else:
        SNOWF = None
        RRR = DATA.RRR.values * mult_factor_RRR

    if make_icestupa :
        DISCHARGE = DATA.DISCHARGE.values
        BETA = DATA.BETA.values
        # FDIF = DATA.FDIF.values

    # Use RRR rather than snowfall?
    if force_use_TP:
        SNOWF = None

    if ('LWin' in DATA) and ('N' in DATA):
        LWin = DATA.LWin.values
        N = DATA.N.values

    elif ('LWin' in DATA):
        LWin = DATA.LWin.values

    else:
        LWin = None
        N = DATA.N.values

    # Use N rather than LWin
    if force_use_N:
        LWin = None

    if ('SLOPE' in DATA):
        SLOPE = DATA.SLOPE.values
    else:
        SLOPE = 0.0

    # Initial cumulative mass balance variable
    MB_cum = 0

    if stake_evaluation:
        # Create pandas dataframe for stake evaluation
        _df = pd.DataFrame(index=stake_data.index, columns=['mb','snowheight'], dtype='float')

    if make_icestupa:
        # Create pandas dataframe for stake evaluation
        _df = pd.DataFrame(index=stake_data.index, columns=[stake_names], dtype='float')

    #--------------------------------------------
    # TIME LOOP
    #--------------------------------------------    
    for t in np.arange(nt):
        
        # Check grid
        GRID.grid_check()

        # get seconds since start
        timestamp = dt*t
        if WRF_X_CSPY:
            timestamp = np.float64(DATA.CURR_SECS.values)

        # Calc fresh snow density
        if (densification_method!='constant'):
            density_fresh_snow = np.maximum(109.0+6.0*(T2[t]-273.16)+26.0*np.sqrt(U2[t]), 50.0)
        else:
            density_fresh_snow = constant_density 

        # Derive snowfall [m] and rain rates [m w.e.]
        if (SNOWF is not None) and (RRR is not None):
            SNOWFALL = SNOWF[t]
            RAIN = RRR[t]-SNOWFALL*(density_fresh_snow/ice_density) * 1000.0
        elif (SNOWF is not None):
            SNOWFALL = SNOWF[t]
        elif make_icestupa : 
            if T2[t] < temperature_threshold_precipitation :
                SNOWFALL = (RRR[t]/1000)*(ice_density/density_fresh_snow)
                RAIN=0
            else:
                RAIN = RRR[t]
                SNOWFALL=0
        else:
            # Else convert total precipitation [mm] to snowheight [m]; liquid/solid fraction
            SNOWFALL = (RRR[t]/1000.0)*(ice_density/density_fresh_snow)*(0.5*(-np.tanh(((T2[t]-zero_temperature) - center_snow_transfer_function) * spread_snow_transfer_function) + 1.0))
            RAIN = RRR[t]-SNOWFALL*(density_fresh_snow/ice_density) * 1000.0

        # Derive Icestupa fountain discharge rates [m w.e.]
        if make_icestupa :
            DISF = DISCHARGE[t]*dt/(60* water_density * np.pi * r_cone**2)
            SNOWFALL *= np.pi * r_cone**2/A_cone
            RAIN *= np.pi * r_cone**2/A_cone

        # if snowfall is smaller than the threshold
        if SNOWFALL<minimum_snowfall :
            SNOWFALL = 0.0

        # if rainfall is smaller than the threshold
        if RAIN<(minimum_snowfall*(density_fresh_snow/ice_density)*1000.0):
            RAIN = 0.0

        if SNOWFALL > 0.0:
           GRID.add_fresh_snow(SNOWFALL, density_fresh_snow, np.minimum(float(T2[t]),zero_temperature), 0.0)
        else:
           GRID.set_fresh_snow_props_update_time(dt)

        # Guarantee that solar radiation is greater equal zero
        if (G[t]<0.0):
            G[t] = 0.0

        #--------------------------------------------
        # Merge grid layers, if necessary
        #--------------------------------------------
        GRID.update_grid()

        #--------------------------------------------
        # Calculate albedo and roughness length changes if first layer is snow
        #--------------------------------------------
        # if DISF > 0:
        #     alpha = albedo_ice
        # else:
        alpha = updateAlbedo(GRID)

        #--------------------------------------------
        # Update roughness length
        #--------------------------------------------
        z0 = updateRoughness(GRID)

        #--------------------------------------------
        # Update surface emissivity coeff
        #--------------------------------------------
        emission_coeff = updateEmissionCoeff(GRID)

        #--------------------------------------------
        # Surface Energy Balance
        #--------------------------------------------
        # Calculate net shortwave radiation
        if make_icestupa :
            f_cone = (0.5* h_cone* r_cone* np.cos(BETA[t])+ np.pi* np.power(r_cone, 2)* 0.5* np.sin(BETA[t])) / A_cone
            SWnet = (1 - alpha) * (cld * G[t] + (1-cld) * G[t] * f_cone)
        else:
            SWnet = G[t] * (1 - alpha)

        # Penetrating SW radiation and subsurface melt
        if SWnet > 0.0 and penetrating_method != 'None' :
            subsurface_melt, G_penetrating = penetrating_radiation(GRID, SWnet, dt)
        else:
            subsurface_melt = 0.0
            G_penetrating = 0.0

        # Calculate residual net shortwave radiation (penetrating part removed)
        sw_radiation_net = SWnet - G_penetrating


        if LWin is not None:
            # Find new surface temperature (LW is used from the input file)
            fun, surface_temperature, lw_radiation_in, lw_radiation_out, sensible_heat_flux, latent_heat_flux, \
                ground_heat_flux, rain_heat_flux, fountain_heat_flux, rho, Lv, MOL, Cs_t, Cs_q, q0, q2 \
                = update_surface_temperature(GRID, dt, z, z0, emission_coeff, T2[t], RH2[t], PRES[t], sw_radiation_net, U2[t],
                                             RAIN, DISF, SLOPE, s_cone, LWin=LWin[t])
        else:
            # Find new surface temperature (LW is parametrized using cloud fraction)
            fun, surface_temperature, lw_radiation_in, lw_radiation_out, sensible_heat_flux, latent_heat_flux, \
                ground_heat_flux, rain_heat_flux, fountain_heat_flux, rho, Lv, MOL, Cs_t, Cs_q, q0, q2 \
                = update_surface_temperature(GRID, dt, z, z0, emission_coeff, T2[t], RH2[t], PRES[t], sw_radiation_net, U2[t],
                                             RAIN, DISF, SLOPE, s_cone, N=N[t])

        #--------------------------------------------
        # Surface mass fluxes [m w.e.q.]
        #--------------------------------------------
        if surface_temperature < zero_temperature:
            sublimation = min(latent_heat_flux / (water_density * lat_heat_sublimation), 0) * dt
            deposition = max(latent_heat_flux / (water_density * lat_heat_sublimation), 0) * dt
            evaporation = 0
            condensation = 0
        else:
            sublimation = 0
            deposition = 0
            evaporation = min(latent_heat_flux / (water_density * lat_heat_vaporize), 0) * dt
            condensation = max(latent_heat_flux / (water_density * lat_heat_vaporize), 0) * dt

        #--------------------------------------------
        # Melt process - mass changes of snowpack (melting, sublimation, deposition, evaporation, condensation)
        #--------------------------------------------
        # Melt energy in [W m^-2 or J s^-1 m^-2]
        melt_energy = max(0, sw_radiation_net + lw_radiation_in + lw_radiation_out + ground_heat_flux + rain_heat_flux +
                          fountain_heat_flux + sensible_heat_flux + latent_heat_flux)

        # Convert melt energy to m w.e.q.
        melt = melt_energy * dt / (1000 * lat_heat_melting)

        # Remove melt [m w.e.q.]
        lwc_from_melted_layers = GRID.remove_melt_weq(melt - sublimation - deposition)

        #--------------------------------------------
        # Freeze process of Icestupa
        #--------------------------------------------
        if DISF > 0:
            freeze_energy = -min(0, sw_radiation_net + lw_radiation_in + lw_radiation_out + ground_heat_flux + rain_heat_flux +
                              fountain_heat_flux + sensible_heat_flux + latent_heat_flux)

            # Fountain droplets use cold content of surface layer
            freeze_energy += GRID.get_node_cold_content(0)/dt

            freeze = freeze_energy * dt / (1000 * lat_heat_melting)

            # Set surface temperature
            GRID.set_node_temperature(0, zero_temperature)

            # Discharge limits new ice layer thickness
            if freeze > DISF + RAIN/1000 :
                freeze = DISF + RAIN/1000
                # print("Warning: Insufficient water for freezing")
                # freeze_energy_remaining = freeze_energy - (DISF + RAIN/1000) * (1000 * lat_heat_melting)/dt
                # new_temp = freeze_energy_remaining/freeze_energy * old_temp
                # # Set surface temperature
                # GRID.set_node_temperature(0, new_temp)
            # else:
            #     # Set surface temperature
            #     GRID.set_node_temperature(0, zero_temperature)


            # New ice layer too small
            if freeze < minimum_snowfall:
                freeze = 0
                freeze_energy = 0
            else:
                # Fountain spray forms ice layer
                GRID.add_fountain_ice(freeze, ice_density, zero_temperature, 0.0)

            Q  = percolation(GRID, DISF-freeze + melt + condensation + RAIN/1000.0 + lwc_from_melted_layers, dt)

        else:
            freeze = 0
            freeze_energy = 0
            Q  = percolation(GRID, melt + condensation + RAIN/1000.0 + lwc_from_melted_layers, dt)

        #--------------------------------------------
        # Refreezing
        #--------------------------------------------
        if make_icestupa :
            water_refreezed = 0
        else:
            water_refreezed = refreezing(GRID)

        #--------------------------------------------
        # Solve the heat equation
        #--------------------------------------------
        solveHeatEquation(GRID, dt)

        #--------------------------------------------
        # Calculate new density to densification
        #--------------------------------------------
        densification(GRID, SLOPE, dt)

        #--------------------------------------------
        # Calculate mass balance
        #--------------------------------------------
        if make_icestupa:
            surface_mass_balance = freeze + SNOWFALL * (density_fresh_snow / ice_density) - melt + sublimation + deposition + evaporation
        else:
            surface_mass_balance = SNOWFALL * (density_fresh_snow / ice_density) - melt + sublimation + deposition + evaporation

        internal_mass_balance = water_refreezed - subsurface_melt
        mass_balance = surface_mass_balance + internal_mass_balance

        internal_mass_balance2 = melt-Q  + subsurface_melt
        mass_balance_check = surface_mass_balance + internal_mass_balance2

        #--------------------------------------------
        # Calculate AIR cone charecteristics
        #--------------------------------------------
        layer_heights = GRID.get_height()
        bulk_temperature = np.average(GRID.get_temperature(), weights=layer_heights)

        rho = np.average(GRID.get_density())
        r_cone, h_cone, s_cone, A_cone, V_cone = update_cone(GRID, surface_mass_balance, r_cone, h_cone,s_cone,
                                                             rho, A_cone, V_cone, radf)

        # Cumulative mass balance for stake evaluation 
        MB_cum = MB_cum + mass_balance
        
        # Store cumulative MB in pandas frame for validation
        if (DATA.isel(time=t).time.values in stake_data.index):
            if stake_names == 'volume':
                _df[stake_names].loc[DATA.isel(time=t).time.values] = V_cone
            elif stake_names == 'area':
                _df[stake_names].loc[DATA.isel(time=t).time.values] = A_cone
                # if drone_evaluation:
                #     # _df['area'].loc[DATA.isel(time=t).time.values] = A_cone
                # elif thermalcam_evaluation:
                #     Tz = bulk_temperature - zero_temperature
                #     _df['bulktemp'].loc[DATA.isel(time=t).time.values] = Tz
                # elif thermistor_evaluation:
                #     Tz = surface_temperature - zero_temperature
                #     _df['temp'].loc[DATA.isel(time=t).time.values] = Tz
                # else:
                #     _df['mb'].loc[DATA.isel(time=t).time.values] = MB_cum 
                #     _df['snowheight'].loc[DATA.isel(time=t).time.values] = GRID.get_total_snowheight() 

        
        # Save results
        _RAIN[t] = RAIN
        _DISF[t] = DISF
        _SNOWFALL[t] = SNOWFALL * (density_fresh_snow/ice_density)
        _LWin[t] = lw_radiation_in
        _LWout[t] = lw_radiation_out
        _H[t] = sensible_heat_flux
        _LE[t] = latent_heat_flux
        _B[t] = ground_heat_flux
        _QRR[t] = rain_heat_flux
        _QFR[t] = fountain_heat_flux
        _MB[t] = mass_balance
        _surfMB[t] = surface_mass_balance
        _Q[t] = Q
        _SNOWHEIGHT[t] = GRID.get_total_snowheight()
        _TOTALHEIGHT[t] = GRID.get_total_height()
        _TS[t] = surface_temperature
        _ALBEDO[t] = alpha
        _SWNET[t] = SWnet
        _NLAYERS[t] = GRID.get_number_layers()
        _ME[t] = melt_energy
        _FE[t] = freeze_energy
        _ICE[t] = freeze
        _intMB[t] = internal_mass_balance
        _EVAPORATION[t] = evaporation
        _SUBLIMATION[t] = sublimation
        _CONDENSATION[t] = condensation
        _DEPOSITION[t] = deposition
        _REFREEZE[t] = water_refreezed
        _subM[t] = subsurface_melt
        _Z0[t] = z0
        _surfM[t] = melt
        _MOL[t] = MOL
        _CONERAD[t] = r_cone
        _CONEHEIGHT[t] = h_cone
        _CONESLOPE[t] = np.degrees(np.arctan(s_cone))
        _CONEAREA[t] = A_cone
        _CONEVOL[t] = V_cone
        _RHO[t] = rho
        _TBULK[t] = bulk_temperature

        if full_field:
            if GRID.get_number_layers()>max_layers:
                print('Maximum number of layers reached')
            else:
                _LAYER_HEIGHT[t, 0:GRID.get_number_layers()] = GRID.get_height()
                _LAYER_RHO[t, 0:GRID.get_number_layers()] = GRID.get_density()
                _LAYER_T[t, 0:GRID.get_number_layers()] = GRID.get_temperature()
                _LAYER_LWC[t, 0:GRID.get_number_layers()] = GRID.get_liquid_water_content()
                _LAYER_CC[t, 0:GRID.get_number_layers()] = GRID.get_cold_content()
                _LAYER_POROSITY[t, 0:GRID.get_number_layers()] = GRID.get_porosity()
                _LAYER_ICE_FRACTION[t, 0:GRID.get_number_layers()] = GRID.get_ice_fraction()
                _LAYER_IRREDUCIBLE_WATER[t, 0:GRID.get_number_layers()] = GRID.get_irreducible_water_content()
                _LAYER_REFREEZE[t, 0:GRID.get_number_layers()] = GRID.get_refreeze()
        else:
            _LAYER_HEIGHT = None
            _LAYER_RHO = None
            _LAYER_T = None
            _LAYER_LWC = None
            _LAYER_CC = None
            _LAYER_POROSITY = None
            _LAYER_ICE_FRACTION = None
            _LAYER_IRREDUCIBLE_WATER = None
            _LAYER_REFREEZE = None

    if stake_evaluation:
        # Evaluate stakes
        _stat = evaluate(stake_names, stake_data, _df)
    elif drone_evaluation:
        # Evaluate stakes
        _stat = evaluate(stake_names, stake_data, _df)
    elif thermistor_evaluation:
        # Evaluate stakes
        _stat = evaluate(stake_names, stake_data, _df)
    elif thermalcam_evaluation:
        # Evaluate stakes
        _stat = evaluate(stake_names, stake_data, _df)
    else:
        _stat = None
        _df = None

    # Restart
    if not WRF_X_CSPY:
        new_snow_height, new_snow_timestamp, old_snow_timestamp = GRID.get_fresh_snow_props()
        RESTART.NLAYERS.values[:] = GRID.get_number_layers()
        RESTART.NEWSNOWHEIGHT.values[:] = new_snow_height
        RESTART.NEWSNOWTIMESTAMP.values[:] = new_snow_timestamp
        RESTART.OLDSNOWTIMESTAMP.values[:] = old_snow_timestamp
        RESTART.LAYER_HEIGHT[0:GRID.get_number_layers()] = GRID.get_height()
        RESTART.LAYER_RHO[0:GRID.get_number_layers()] = GRID.get_density()
        RESTART.LAYER_T[0:GRID.get_number_layers()] = GRID.get_temperature()
        RESTART.LAYER_LWC[0:GRID.get_number_layers()] = GRID.get_liquid_water_content()
        RESTART.LAYER_IF[0:GRID.get_number_layers()] = GRID.get_ice_fraction()

    return (indY,indX,RESTART,_RAIN,_DISF,_SNOWFALL,_LWin,_LWout,_H,_LE,_B, _QRR,_QFR, \
            _MB,_surfMB,_Q,_SNOWHEIGHT,_TOTALHEIGHT,_TS,_ALBEDO, _SWNET, _NLAYERS, \
            _ME,_FE,_ICE,_intMB,_EVAPORATION,_SUBLIMATION,_CONDENSATION,_DEPOSITION,_REFREEZE, \
            _subM,_Z0,_surfM, _MOL, _CONERAD, _CONEHEIGHT, _CONESLOPE, _CONEAREA, _CONEVOL, _RHO, _TBULK, \
            _LAYER_HEIGHT,_LAYER_RHO,_LAYER_T,_LAYER_LWC,_LAYER_CC,_LAYER_POROSITY,_LAYER_ICE_FRACTION, \
            _LAYER_IRREDUCIBLE_WATER,_LAYER_REFREEZE,stake_names,_stat,_df)
