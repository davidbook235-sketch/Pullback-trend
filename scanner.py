import yfinance as yf
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import time
import streamlit as st

# ---- Fallback Nifty 50 list agar NSE se download fail ho jaye ----
# Cloud servers par NSE archive block karta hai, isliye fallback zaroori hai
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

def load_universe(choice="nifty50"):
    if choice == "nifty50":
        return NIFTY_FALLBACK
    # Agar future me Nifty 500 chahiye toh yahan expand kar sakte hain
    return NIFTY_FALLBACK

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
        
        # MultiIndex columns ko flatten karein
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
            
        nifty["EMA200"] = nifty["Close"].ewm(span=200, adjust=False).mean()
        
        # Values ko safely scalar me convert karein
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

        # Values ko scalar me convert karein
        close = float(last["Close"])
        ema20 = float(last["EMA20"])
        ema50 = float(last["EMA50"])
        ema200 = float(last["EMA200"])
        rsi = float(last["RSI"])
        vol_ratio = float(last["Vol_Ratio"])
        atr = float(last["ATR"])
        prev_high = float(prev["High"])

        # --- Trend filters ---
        if not (close > ema50 > ema200):
            return None
        if not (ema20 > ema50):
            return None

        # --- RSI range ---
        if not (40 <= rsi <= 55):
            return None

        # --- Pullback to EMA20 ---
        dist_ema20 = abs(close - ema20) / ema20 * 100
        if dist_ema20 > 3:
            return None

        # --- Volume dry-up in pullback ---
        recent_vol = df["Volume"].iloc[-5:].mean()
        vol_ma20 = float(last["Vol_MA20"])
        if recent_vol > vol_ma20 * 0.8:
            return None

        # --- VCP check (3 contractions with narrowing ranges) ---
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

        # --- Entry trigger: breakout > prev day high + Vol 1.5x ---
        if not (close > prev_high and close > ema20):
            return None
        if vol_ratio < 1.5:
            return None

        # --- Calculate levels ---
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
def run_scan(universe="nifty50", progress_cb=None):
    if not is_market_ok():
        return [], "Market filter failed: Nifty 50 is below 200 DMA. Naye trades avoid karein."

    symbols = load_universe(universe)
    results = []
    
    for i, sym in enumerate(symbols):
        if progress_cb:
            progress_cb(i / len(symbols), sym)
        
        res = scan_stock(sym)
        if res:
            results.append(res)
            
        time.sleep(0.5) # Rate limit se bachne ke liye 0.5 sec delay
        
    return results, None
