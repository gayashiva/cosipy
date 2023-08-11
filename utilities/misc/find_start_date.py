import pandas as pd
from datetime import datetime, timedelta

# Load CSV data into DataFrames
df1 = pd.read_csv('../../data/input/altiplano20/altiplano_2019.csv')
print(df1)

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

for date, temp in daily_min_temps.iteritems():
    if temp < 0:
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
combined_df = pd.concat([df1, df2])
combined_df['TIMESTAMP'] = pd.to_datetime(combined_df['TIMESTAMP'])
combined_df.set_index('TIMESTAMP', inplace=True)
# print(combined_df)
combined_df = combined_df[start_date:start_date + timedelta(days=365)]
print(combined_df.tail())
combined_df= combined_df.reset_index()
combined_df['Discharge'] = 60

combined_df.to_csv('../../data/input/altiplano20/input.csv')
