import yfinance as yf
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import time

# ---- Nifty 500 stock list ----
NIFTY500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"

def load_nifty500():
    df = pd.read_csv(NIFTY500_URL)
    symbols = df["Symbol"].astype(str).str.strip() + ".NS"
    return symbols.tolist()

# ---- Indicator helpers ----
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

# ---- Market filter ----
def is_market_ok():
    nifty = yf.download("^NSEI", period="1y", interval="1d", progress=False)
    if nifty.empty:
        return False
    nifty["EMA200"] = nifty["Close"].ewm(span=200, adjust=False).mean()
    return nifty["Close"].iloc[-1] > nifty["EMA200"].iloc[-1]

# ---- Main scan function ----
def scan_stock(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d", progress=False, threads=False)
        if df.empty or len(df) < 200:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = add_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # --- Trend filters ---
        if not (last["Close"] > last["EMA50"] > last["EMA200"]):
            return None
        if not (last["EMA20"] > last["EMA50"]):
            return None

        # --- RSI range ---
        if not (40 <= last["RSI"] <= 55):
            return None

        # --- Pullback to EMA20 ---
        dist_ema20 = abs(last["Close"] - last["EMA20"]) / last["EMA20"] * 100
        if dist_ema20 > 3:
            return None

        # --- Volume dry-up in pullback ---
        recent_vol = df["Volume"].iloc[-5:].mean()
        if recent_vol > last["Vol_MA20"] * 0.8:
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

        # --- Entry trigger: bounce from EMA20 + breakout of prev day high ---
        if not (last["Close"] > prev["High"] and last["Close"] > last["EMA20"]):
            return None
        if last["Vol_Ratio"] < 1.5:
            return None

        # --- Calculate levels ---
        swing_low = df["Low"].iloc[-10:].min()
        atr_stop = last["Close"] - 1.5 * last["ATR"]
        stop_loss = max(swing_low, atr_stop)
        risk = last["Close"] - stop_loss
        target = last["Close"] + 3 * risk

        return {
            "Symbol": symbol.replace(".NS", ""),
            "CMP": round(last["Close"], 2),
            "RSI": round(last["RSI"], 1),
            "Vol_Ratio": round(last["Vol_Ratio"], 2),
            "Stop_Loss": round(stop_loss, 2),
            "Target": round(target, 2),
            "Risk_Reward": "1:3",
            "Contractions": len(ranges),
            "EMA20_Dist_%": round(dist_ema20, 2),
        }
    except Exception:
        return None

def run_scan(universe="nifty500", max_stocks=100, progress_cb=None):
    if not is_market_ok():
        return [], "Market filter failed: Nifty 50 is below 200 DMA. Naye trades avoid karein."

    if universe == "nifty50":
        symbols = load_nifty500()[:50]
    elif universe == "nifty200":
        symbols = load_nifty500()[:200]
    else:
        symbols = load_nifty500()

    symbols = symbols[:max_stocks]
    results = []
    for i, sym in enumerate(symbols):
        if progress_cb:
            progress_cb(i / len(symbols), sym)
        res = scan_stock(sym)
        if res:
            results.append(res)
        time.sleep(0.1)
    return results, None
