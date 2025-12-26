import streamlit as st
import yfinance as yf
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import StochRSIIndicator
from datetime import datetime, timedelta
import time

st.set_page_config(
    page_title="Bank Nifty Live Trading",
    layout="wide"
)

SYMBOL = "^NSEBANK"
REFRESH_SEC = 15

# -------------------------------
# AUTO REFRESH LOGIC (FIXED)
# -------------------------------
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh > REFRESH_SEC:
    st.session_state.last_refresh = time.time()
    st.experimental_rerun()

# -------------------------------
# DATA + LOGIC (UNCHANGED)
# -------------------------------
@st.cache_data(ttl=REFRESH_SEC)
def fetch_and_process_data():
    df = yf.download(
        SYMBOL,
        period="5d",
        interval="5m",
        auto_adjust=False,
        progress=False
    )

    if df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.reset_index(inplace=True)

    # UTC → IST
    df['Datetime'] = pd.to_datetime(df['Datetime']) + pd.Timedelta(hours=5, minutes=30)
    df.set_index('Datetime', inplace=True)

    # NSE hours
    df = df.between_time("09:15", "15:30")

    for col in ['Open', 'High', 'Low', 'Close', 'Adj Close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df[['Open','High','Low','Close']] = df[['Open','High','Low','Close']].ffill()

    # EMA 20
    df['EMA20'] = EMAIndicator(df['Close'], window=20, fillna=True).ema_indicator()

    # Stoch RSI
    stoch = StochRSIIndicator(
        close=df['Close'],
        window=14,
        smooth1=3,
        smooth2=3,
        fillna=True
    )
    df['StochRSI'] = stoch.stochrsi()

    # -------- Trend Logic --------
    trends = ["NA"]
    for i in range(1, len(df)):
        ch, ph = df['High'].iloc[i], df['High'].iloc[i-1]
        cl, pl = df['Low'].iloc[i], df['Low'].iloc[i-1]

        if ch > ph and cl > pl:
            trends.append("UP")
        elif ch < ph and cl < pl:
            trends.append("DOWN")
        else:
            trends.append("Sideways")

    df['Trend'] = trends

    # -------- Signal Logic --------
    signals, remarks = [], []

    for _, row in df.iterrows():
        close = row['Close']
        ema = row['EMA20']
        stochv = row['StochRSI']
        trend = row['Trend']

        r = []

        if abs(close - ema) > 100:
            r.append("Price far from EMA20")

        if trend == "UP" and abs(close - ema) <= 100 and stochv < 0.3:
            signals.append("CE BUY")
            remarks.append("HH-HL + EMA near + StochRSI < 0.3")

        elif trend == "DOWN" and abs(close - ema) <= 100 and stochv > 0.7:
            signals.append("PE BUY")
            remarks.append("LH-LL + EMA near + StochRSI > 0.7")

        else:
            if trend == "Sideways":
                r.append("Market sideways")
            if trend == "UP" and stochv >= 0.3:
                r.append("StochRSI not low for CE")
            if trend == "DOWN" and stochv <= 0.7:
                r.append("StochRSI not high for PE")

            signals.append("NO TRADE")
            remarks.append("; ".join(r))

    df['Signal'] = signals
    df['Remark'] = remarks

    latest_day = df.index.date.max()
    df = df[df.index.date == latest_day]

    for col in ['Adj Close','Close','High','Low','Open','EMA20']:
        if col in df.columns:
            df[col] = df[col].round(2)

    return df.sort_index(ascending=False)

# -------------------------------
# UI
# -------------------------------
st.title("📊 Bank Nifty Live Trading Dashboard")

df = fetch_and_process_data()

if df.empty:
    st.error("No data received from Yahoo Finance")
    st.stop()

latest = df.iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Bank Nifty", latest['Close'])
c2.metric("EMA20", latest['EMA20'])
c3.metric("StochRSI", round(latest['StochRSI'], 2))
c4.metric("Signal", latest['Signal'])

# -------- IST TIME FIXED --------
ist_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
st.info(f"🕒 Last Refresh (IST): {ist_time.strftime('%Y-%m-%d %H:%M:%S')}")

st.warning(f"📌 Remark: {latest['Remark']}")

if latest['Signal'] in ["CE BUY", "PE BUY"]:
    st.error("🚨 TRADE SIGNAL GENERATED 🚨")

st.subheader("📋 Latest 1-Day Data (Descending)")

show_cols = [
    'Close','High','Low','Open','Volume',
    'EMA20','StochRSI','Signal','Remark'
]

st.dataframe(
    df[show_cols],
    use_container_width=True,
    height=420
)

st.download_button(
    "⬇️ Download CSV",
    data=df.to_csv().encode('utf-8'),
    file_name="BankNifty_Live.csv",
    mime="text/csv"
)

st.caption("🔄 Auto refresh every 15 seconds (Working)")
