import sys
import pandas as pd
from tqdm import tqdm
import numpy as np
import math
from datetime import datetime, timedelta
from solar import get_solar
sys.path.append('../../')
from config import plat, plon, hgt, cld

# Load CSV data into DataFrames
df1 = pd.read_csv('../../data/input/altiplano20/altiplano_2019.csv')

# Convert to DateTime
df1['TIMESTAMP'] = pd.to_datetime(df1['TIMESTAMP'])

# Set DateTime as index
df1.set_index('TIMESTAMP', inplace=True)

# Resample to daily minimum temperature
daily_min_temps = df1['temp'].resample('D').min()

# Find longest consecutive period
longest_period = 0
current_period = 0
start_date = None
crit_temp = -3

for date, temp in daily_min_temps.iteritems():
    if temp < crit_temp:
        current_period += 1
        if current_period > longest_period:
            longest_period = current_period
            start_date = date - pd.DateOffset(days=current_period - 1)
    else:
        current_period = 0

print("Start Date:", start_date)
print("Longest Consecutive Days:", longest_period)

df2 = pd.read_csv('../../data/input/altiplano20/altiplano_2020.csv')

# Combine DataFrames
df1 = df1.reset_index()
df = pd.concat([df1, df2])
df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'])
df.set_index('TIMESTAMP', inplace=True)
df = df[start_date:start_date + timedelta(days=365)]
df['Discharge'] = 60
print(df.columns)

solar_df = get_solar(
    coords=[plat,plon],
    start=df.index[0],
    end=df.index[-1],
    DT=60*60,
    alt=hgt,
)

df = pd.merge(solar_df, df, on="TIMESTAMP", how="left")

if "SW_global" not in list(df.columns):
    df["SW_global"] = df["ghi"]
    print(f"Estimated global solar from pvlib\n")

# df["SW_direct"] = (1- cld) * df["SW_global"]
# df["SW_diffuse"] = cld * df["SW_global"]
# print(f"Estimated solar components with constant cloudiness of {cld}\n")

#Constants

sigma = 5.67e-08

for row in tqdm(
    df.itertuples(),
    total=df.shape[0],
    desc="Creating AIR input...",
):
    i = row.Index

    """ Vapour Pressure"""
    df.loc[i, "vp_a"] = np.exp(
        34.494 - 4924.99/ (row.temp + 237.1)
    ) / ((row.temp + 105) ** 1.57 * 100)
    df.loc[i, "vp_a"] *= row.RH/100

    """LW incoming"""
    df.loc[i, "e_a"] = (
        1.24
        * math.pow(abs(df.loc[i, "vp_a"] / (row.temp + 273.15)), 1 / 7)
    ) * (1 + 0.22 * math.pow(cld, 2))

    df.loc[i, "LW_in"] = (
        df.loc[i, "e_a"] * sigma * math.pow(row.temp + 273.15, 4)
    )

df = df.round(3)

if df.isnull().values.any():
    for column in df.columns:
        if df[column].isna().sum() > 0:
            print(" Null values interpolated in %s" % column)
            df.loc[:, column] = df[column].interpolate()

df= df.reset_index()
print(df.head())
df.to_csv('../../data/input/altiplano20/input.csv')
