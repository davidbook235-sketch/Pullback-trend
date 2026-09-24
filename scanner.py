import yfinance as yf
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import time
import streamlit as st
import requests
from io import StringIO

# ---- Fallback Nifty 50 list agar NSE se download fail ho jaye ----
NIFTY_FALLBACK = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "BAJFINANCE.NS", "LT.NS", "HCLTECH.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS",
    "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "M&M.NS", "TATAMOTORS.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS",
    "BAJAJFINSV.NS", "GRASIM.NS", "HINDALCO.NS", "DRREDDY.NS", "CIPLA.NS",
    "NESTLEIND.NS", "BRITANNIA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "DIVISLAB.NS",
    "APOLLOHOSP.NS", "INDUSINDBK.NS", "BAJAJ-AUTO.NS", "TATACONSUM.NS", "SBILIFE.NS",
    "HDFCLIFE.NS", "LTIM.NS", "TECHM.NS", "SHRIRAMFIN.NS", "BPCL.NS"
]

# ---- NSE se dynamically symbols fetch karna (Nifty 250 / 500 ke liye) ----
@st.cache_data(ttl=86400) # 24 ghante tak cache rahega, baar baar download nahi karega
def fetch_nse_symbols(index_name):
    # NSE ki official website se CSV download karne ki koshish
    urls = {
        "nifty250": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
        "nifty500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    }
    
    url = urls.get(index_name)
    if not url:
        return []
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(StringIO(response.text))
            # NSE CSV me 'Symbol' column hota hai
            symbols = df["Symbol"].dropna().astype(str).str.strip() + ".NS"
            symbols = symbols.tolist()
            
            # Nifty 250 ke liye sirf top 250 le lo, Nifty 500 ke liye saare 500
            if index_name == "nifty250":
                return symbols[:250]
            return symbols
        else:
            return []
    except Exception as e:
        print(f"NSE fetch error: {e}")
        return []

# ---- Cached Data Download (Streamlit Cloud par rate limit se bachne ke liye) ----
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d", progress=False, threads=False)
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_market_data():
    try:
        df = yf.download("^NSEI", period="1y", interval="1d", progress=False, threads=False)
        return df
    except Exception:
        return pd.DataFrame()

# ---- Universe Loader ----
def load_universe(choice="nifty50"):
    if choice == "nifty50":
        return NIFTY_FALLBACK, "Nifty 50 (Fallback list)"
    
    symbols = fetch_nse_symbols(choice)
    
    if len(symbols) > 50:
        return symbols, f"{choice.upper()} ({len(symbols)} stocks from NSE)"
    else:
        # Agar NSE se fetch fail ho jaye toh fallback
        return NIFTY_FALLBACK, "Nifty 50 (NSE fetch failed, using fallback)"

# ---- Indicator Calculation ----
def add_indicators(df):
    close = df["Close"]
    df["EMA20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()
    df["EMA200"] = close.ewm(span=200, adjust=False).mean()
    df["RSI"] = RSIIndicator(close, window=14).rsi()
    df["ATR"] = AverageTrueRange(df["High"], df["Low"], close, window=14).average_true_range()
    df["Vol_MA20"] = df["Volume"].rolling(20).mean()
    df["Vol_Ratio"] = df["Volume"] / df["Vol_MA20"]
    return df

# ---- Market Filter ----
def is_market_ok():
    try:
        nifty = get_market_data()
        if nifty is None or nifty.empty:
            return False
        
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
            
        nifty["EMA200"] = nifty["Close"].ewm(span=200, adjust=False).mean()
        
        last_close = float(nifty["Close"].iloc[-1])
        last_ema = float(nifty["EMA200"].iloc[-1])
        
        return last_close > last_ema
    except Exception as e:
        print(f"Market filter error: {e}")
        return False

# ---- Main Stock Scanner ----
def scan_stock(symbol):
    try:
        df = get_stock_data(symbol)
        
        if df is None or df.empty or len(df) < 200:
            return None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = add_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(last["Close"])
        ema20 = float(last["EMA20"])
        ema50 = float(last["EMA50"])
        ema200 = float(last["EMA200"])
        rsi = float(last["RSI"])
        vol_ratio = float(last["Vol_Ratio"])
        atr = float(last["ATR"])
        prev_high = float(prev["High"])

        if not (close > ema50 > ema200):
            return None
        if not (ema20 > ema50):
            return None

        if not (40 <= rsi <= 55):
            return None

        dist_ema20 = abs(close - ema20) / ema20 * 100
        if dist_ema20 > 3:
            return None

        recent_vol = df["Volume"].iloc[-5:].mean()
        vol_ma20 = float(last["Vol_MA20"])
        if recent_vol > vol_ma20 * 0.8:
            return None

        ranges = []
        window = 10
        for i in range(3, 0, -1):
            seg = df.iloc[-(i * window + 1):-(i - 1) * window if i > 1 else None]
            if len(seg) < 5:
                continue
            rng = (seg["High"].max() - seg["Low"].min()) / seg["Low"].min() * 100
            ranges.append(rng)
            
        if len(ranges) >= 2:
            for j in range(1, len(ranges)):
                if ranges[j] >= ranges[j - 1] * 0.9:
                    return None
        else:
            return None

        if not (close > prev_high and close > ema20):
            return None
        if vol_ratio < 1.5:
            return None

        swing_low = df["Low"].iloc[-10:].min()
        atr_stop = close - 1.5 * atr
        stop_loss = max(swing_low, atr_stop)
        risk = close - stop_loss
        target = close + 3 * risk

        return {
            "Symbol": symbol.replace(".NS", ""),
            "CMP": round(close, 2),
            "RSI": round(rsi, 1),
            "Vol_Ratio": round(vol_ratio, 2),
            "Stop_Loss": round(stop_loss, 2),
            "Target": round(target, 2),
            "Risk_Reward": "1:3",
            "Contractions": len(ranges),
            "EMA20_Dist_%": round(dist_ema20, 2),
        }
    except Exception as e:
        print(f"Error scanning {symbol}: {e}")
        return None

# ---- Run Scan ----
def run_scan(universe_choice="nifty50", progress_cb=None):
    if not is_market_ok():
        return [], "Market filter failed: Nifty 50 is below 200 DMA. Naye trades avoid karein."

    symbols, source_info = load_universe(universe_choice)
    results = []
    
    # Rate limit se bachne ke liye delay adjust karein
    # Bade universe ke liye thoda zyada delay taaki Yahoo block na kare
    delay = 0.5 if len(symbols) <= 50 else 0.3 
    
    for i, sym in enumerate(symbols):
        if progress_cb:
            progress_cb(i / len(symbols), sym, len(symbols))
        
        res = scan_stock(sym)
        if res:
            results.append(res)
            
        time.sleep(delay)
        
    return results, None, source_info
