import pandas as pd
import numpy as np
from yahooquery import Ticker
import os
import time
import math

fx_cache = {}

def cap_floor(val, min_val, max_val): #Define bounds for val
    return max(min(val, max_val), min_val)

def get_latest(df_sorted, field, max_lookback=4): #Reads a single value from the financial statement
    if field not in df_sorted.columns:
        return 0
    for i in range(1, max_lookback + 1):
        try:
            value = df_sorted.iloc[-i].get(field, None)
            if pd.notnull(value):
                return value
        except IndexError:
            break  
    return 0

def get_balance(latest_bs, fields): #Returns a single value from the balance sheet 
    total_value = 0
    for f in fields:
        if f in latest_bs:
            val = latest_bs.get(f, 0)
            total_value += val if pd.notna(val) else 0
    return total_value

def get_series(df, fields, min_periods=2): #Get a multiple entries from the financial statement
    if df is None or df.empty:
        return None

    series = pd.Series(0, index=df.index, dtype="float64")
    for f in fields:
        if f in df.columns:
            val = pd.to_numeric(df[f], errors='coerce').fillna(0)
            series += val
    series = series.replace(0, pd.NA).dropna()
    if len(series) >= min_periods:
        return series.sort_index()
    return None



# ------------------- Compute -------------------



def compute_value(ticker): #Gets Estimated Price
    stock = Ticker(ticker)
    
    #Income and Cashflow Statements
    income_df = stock.income_statement(frequency='annual', trailing=False).sort_values('asOfDate')
    cf_df = stock.cash_flow(frequency='annual', trailing=False).sort_values('asOfDate')
    Revenue = get_latest(income_df, "OperatingRevenue")
    Interest = get_latest(income_df, "InterestExpense")
    OperatingIncome = get_latest(income_df, "OperatingIncome")
    CFFO = get_latest(cf_df, "CashFlowFromContinuingOperatingActivities")

    #Balance sheet
    latest_bs = stock.balance_sheet(frequency='annual').sort_values('asOfDate').iloc[-1]
    cash = get_balance(latest_bs, ['CashCashEquivalentsAndShortTermInvestments'])
    if cash == 0: get_balance(lastest_bs, ['CashAndCashEquivalents', 'ShortTermInvestments', 'OtherShortTermInvestments'])
    debt = get_balance(latest_bs, ['CurrentDebt', 'LongTermDebt']) 
    mezzaine = get_balance(latest_bs, ['MinorityInterest', 'PreferredStock'])
    liabilities = get_balance(latest_bs, ['TotalLiabilitiesNetMinorityInterest'])
    equity = get_balance(latest_bs, ['TotalEquityGrossMinorityInterest'])
    assets = equity + debt - cash 

    #FX_rate (only for foreign companies)
    fx_rate = 1
    currency = income_df.iloc[-1]['currencyCode']
    if currency.upper() != 'USD':
        if currency.upper() in fx_cache:
            fx_rate = fx_cache[currency.upper()]
        else:
            fx_ticker = Ticker(f"{currency.upper()}USD=X")
            fx_data = fx_ticker.price
            fx_rate = fx_data[f"{currency.upper()}USD=X"]['regularMarketPrice']
            fx_cache[currency.upper()] = fx_rate

    #Number of common shares outstanding
    price_data = stock.price.get(ticker, {})
    price = price_data.get("regularMarketPrice")
    mc = price_data.get('marketCap')
    shares = mc/price
    
    #Revenue Growth
    rev_series = get_series(income_df, ['OperatingRevenue'])
    rev_past = rev_series.iloc[-2]
    rev_now = rev_series.iloc[-1]
    rev_growth = (rev_now/rev_past-1)

    #Multiples
    cur_margin = OperatingIncome/Revenue if Revenue >0 else -999
    roic = (OperatingIncome)*0.8/assets if assets>0 else 999
    roa = (CFFO)/assets if assets>0 else 999
    e = ( len(str(max(int(Revenue*fx_rate), 0))) - 1 - 3 ) / 10
    #debt_equity = liabilities/equity if equity>0 else 999
    dol = Interest/OperatingIncome if OperatingIncome>0 else 999
            
    #Discount Rate
    r_bound = 0.01
    discount = 0.05*3
    x = 0
    x -= cap_floor(rev_growth/100, -r_bound, r_bound) #Revenue
    x -= cap_floor(cur_margin/100, -r_bound, r_bound) #Margins
    x -= cap_floor(roic/100, -r_bound, r_bound) #Efficiency
    x -= cap_floor(roa/100, -r_bound, r_bound) #Efficiency
    x -= cap_floor(e/100, -r_bound, r_bound) #Size
    #x += cap_floor((debt_equity-1)/100, 0, r_bound) #Financial risk
    x += cap_floor(dol/100, 0, r_bound) #Operating Leverage (fixed cost)
    discount += x*3
    
    #Defines free parameters for each scenario (bear, base, bull)
    values = [-1, -1, -1]
    rev_gs = [-1, -1, -1]
    margin_ds = [-1, -1, -1]
    rev_mins = [-0.03, 0.01, 0.05]
    rev_maxes = [0.02, 0.1, 0.18] 
    rev_mults = [0.1, 0.45, 0.8]
    margin_mins = [x/2 for x in rev_mins]
    margin_maxes = [x/2 for x in rev_maxes]
    margin_mults = [x/2 for x in rev_mults] #40 70 180
    n = 10
    for i in range(3):
        rev_min = rev_mins[i]
        rev_max = rev_maxes[i]
        rev_mult = rev_mults[i]
        margin_min = margin_mins[i]
        margin_max = margin_maxes[i]
        margin_mult = margin_mults[i]
        if rev_growth<0 and i==0: rev_mult = rev_mults[2] 
        if max(roa, roic)<0 and i==0: margin_mult = margin_mults[2]
        if(i==0): r = cap_floor(discount, 0.1, 0.2)
        elif(i==1): r = cap_floor(discount, 0.08, 0.15)
        elif(i==2): r = cap_floor(discount, 0.06, 0.1)
        
        rev_g = cap_floor(rev_growth*rev_mult, rev_min, rev_max) #Estimates revenue growth for next n years
        margin_d = cap_floor((max(roa, roic)*margin_mult/100)*n, margin_min, margin_max) #Estimates margin expansion for the next n years
        margin_g = margin_d/n
        rev_gs[i] = round(rev_g*100, 0)
        margin_ds[i] = round(margin_d*100, 0)
    
        #Growing Annuity
        ga = 0
        Margin = 0 if(cur_margin<0 and i==2) else cur_margin
        for t in range(1, n + 1):
            Revenue *= (1+rev_g) 
            Margin += margin_g
            if Margin>=1: Margin=0.99
            Interest = 0#*= (1+rev_g)
            cf_t = (Revenue * Margin - Interest)*.8 #Assuming 20% tax rate
            pv_t = cf_t / ((1 + r) ** t)
            ga += pv_t
            
        #Terminal Value
        g = i/100 
        C = cf_t*(1+g)
        tv = (C)/(r-g)
        tv = tv/((1+r)**(n))
        if(tv<0): tv=0
        npv = ga + tv
        npv = npv + cash - debt - mezzaine #use debt instead of interest
        npv*= fx_rate
        try: npv = round(npv/shares, 2)
        except: npv = -1
        values[i] = round(npv, 2) #Estimated intrinsic value of each share (Price)
    return values[0], values[1], values[2], round(discount*100, 2), rev_gs[0], rev_gs[1], rev_gs[2], margin_ds[0], margin_ds[1], margin_ds[2]

def compute_price(ticker): #Gets Market Price
    stock = Ticker(ticker)
    price_data = stock.price.get(ticker, {})
    price = price_data.get("regularMarketPrice")
    mc = price_data.get('marketCap')
    if(mc/1000000 < 100): return -1
    return price

