import time
import os
import pandas as pd
from yahooquery import Ticker
from financial_utils import (
    compute_value,
    compute_price
)
from tqdm import tqdm



# ------------------- Load Existing Data -------------------



csv_path = "factor_scores.csv"
existing_data = {} 
FIELDS = ["Price", "Bear", "Base", "Bull", "Discount Raw", "Rev_g0", "Rev_g1", "Rev_g2", "Margin_d0", "Margin_d1", "Margin_d2"]

if os.path.exists(csv_path): #Reads data from csv file
    try:
        df_existing = pd.read_csv(csv_path)
        print(f"Loaded {len(df_existing)} rows from {csv_path}\n")

        for _, row in df_existing.iterrows():
            ticker = row["Ticker"].upper()
            existing_data[ticker] = {}
            for field in FIELDS:
                value = row.get(field)
                if pd.notna(value):
                    existing_data[ticker][field] = value
    except Exception as e:
        print(f"Error reading existing CSV: {e}")



# ------------------- Load Tickers -------------------



tickers = []
with open("tickers.txt", "r") as file: #Reads tickers from text file 
    for line in file:
        symbol = line.strip().upper()
        if symbol == "END":
            break
        if symbol:
            tickers.append(symbol)
        time.sleep(0.05)



# ------------------- Collect Data -------------------



data = []
for symbol in tqdm(tickers):
    existing_fields = existing_data.get(symbol, {})
    missing_fields = [f for f in FIELDS if f not in existing_fields] #Gets list of missing fields not in the csv file

    if not missing_fields:
        record = {"Ticker": symbol}
        record.update(existing_fields)
        data.append(record)
        continue

    print(symbol)
    try: #Calculates the values for the missing fields
        computed_fields = {}
        if "Price" in missing_fields:
            try:
                computed_fields["Price"] = compute_price(symbol)
            except Exception as e:
                print(f"{symbol}: Error computing Price → {e}")

        missing_value_fields = [f for f in FIELDS[1:] if f in missing_fields]
        if missing_value_fields:
            try:
                values = compute_value(symbol) #Calculates the missing field using the function from the financial_util.py file
                for field, val in zip(FIELDS[1:], values):
                    #if field in missing_value_fields: 
                    computed_fields[field] = val
            except Exception as e:
                print(f"{symbol}: Error computing value fields → {e}")

        #Merge and validate
        record = {"Ticker": symbol}
        record.update(existing_fields)
        record.update(computed_fields)
        if all(field in record for field in FIELDS):
            data.append(record)
        else:
            print(f"{symbol}: Skipped due to incomplete factor set")

    except Exception as e:
        print(f"Error processing {symbol}: {e}")
    time.sleep(0.5)



# ------------------- Save Final Scores -------------------



final_scores = []
for d in data:
    record = {"Ticker": d["Ticker"]}
    for field in FIELDS:
        try:
            record[field] = round(d[field], 2)
        except:
            record[field] = d[field]
    final_scores.append(record)

csv_path = str(input("Enter name: ")) + ".csv"
if csv_path == "0.csv":
    csv_path = "factor_scores.csv"
else:
    csv_path = os.path.join("store", csv_path)

df_final = pd.DataFrame(final_scores)   #Update csv file with new results
df_final.to_csv(csv_path, index=False)
print(f"\nSaved updated results to {csv_path}") 










