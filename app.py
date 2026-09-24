import streamlit as st
import pandas as pd
from scanner import run_scan

st.set_page_config(
    page_title="Swing Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Mobile-friendly CSS
st.markdown("""
<style>
    .main .block-container {padding: 1rem 0.5rem; max-width: 100%;}
    .stDataFrame {font-size: 12px;}
    div[data-testid="stMetricValue"] {font-size: 18px;}
    .stButton > button {width: 100%;}
    @media (max-width: 768px) {
        h1 {font-size: 20px !important;}
        .stDataFrame {font-size: 11px;}
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 Swing Trade Scanner")
st.caption("Trend Pullback + VCP Filter | Nifty 500")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    universe = st.selectbox("Universe", ["nifty50", "nifty200", "nifty500"])
    max_stocks = st.slider("Max Stocks to Scan", 20, 500, 100, 10)
    st.markdown("---")
    st.markdown("""
    **Strategy Rules:**
    - Price > EMA50 > EMA200
    - EMA20 > EMA50
    - RSI 40-55
    - Pullback to EMA20 (<3%)
    - Volume dry-up
    - VCP: 3 narrowing contractions
    - Breakout > prev high + Vol 1.5x
    """)

# Main
if st.button("🔍 Run Scanner", type="primary"):
    progress_bar = st.progress(0)
    status = st.empty()

    def update_progress(pct, sym):
        progress_bar.progress(min(pct, 1.0))
        status.text(f"Scanning: {sym}")

    with st.spinner("Scanning stocks..."):
        results, error = run_scan(universe, max_stocks, update_progress)

    progress_bar.empty()
    status.empty()

    if error:
        st.error(error)
    elif results:
        st.success(f"✅ {len(results)} stocks mile!")
        df = pd.DataFrame(results)
        df = df.sort_values("Vol_Ratio", ascending=False).reset_index(drop=True)
        st.dataframe(df, use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv, "swing_scan_results.csv", "text/csv")
    else:
        st.warning("Koi stock nahi mila. Filters dheele karein ya baad me try karein.")

st.markdown("---")
st.caption("⚠️ Educational tool only. Not financial advice. Data via yfinance.")
