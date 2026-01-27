import streamlit as st
import pandas as pd
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from io import StringIO

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(layout="wide")

POLYGON_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

SLEEP = 0.25
BATCH_SIZE = 15          # envoi CSV tous les X setups
HEARTBEAT_EVERY = 25     # message Discord toutes les X analyses

# =====================================================
# SESSION HTTP ROBUSTE
# =====================================================
def build_session():
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session

SESSION = build_session()

# =====================================================
# DISCORD
# =====================================================
def send_message(msg):
    payload = {"content": msg[:1900]}
    r = SESSION.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    st.write("Discord msg:", r.status_code)

def send_csv(df):
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    files = {
        "file": ("scanner_results.csv", csv_buffer.getvalue(), "text/csv")
    }

    r = SESSION.post(DISCORD_WEBHOOK, files=files, timeout=15)
    st.write("Discord CSV:", r.status_code)

# =====================================================
# DATA
# =====================================================
@st.cache_data
def load_tickers():
    df = pd.read_excel("russell3000_constituents.xlsx")
    return (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .str.upper()
        .tolist()
    )

@st.cache_data(ttl=900)
def get_sma(ticker, window):
    url = (
        f"https://api.polygon.io/v1/indicators/sma/{ticker}"
        f"?timespan=day&window={window}&series_type=close"
        f"&adjusted=true&order=desc&limit=2&apiKey={POLYGON_KEY}"
    )
    try:
        r = SESSION.get(url, timeout=10).json()
        values = r.get("results", {}).get("values", [])
        if len(values) < 2:
            return None, None
        return values[0]["value"], values[1]["value"]
    except:
        return None, None

@st.cache_data(ttl=300)
def get_price(ticker):
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={POLYGON_KEY}"
        r = SESSION.get(url, timeout=10).json()
        return r["results"][0]["c"]
    except:
        return None

# =====================================================
# SCORE
# =====================================================
def compute_score(dist, slope, golden):
    score = 0
    score += max(0, 40 - abs(dist) * 10)
    score += min(30, abs(slope) * 200)
    if golden:
        score += 20
    return round(min(100, score), 1)

# =====================================================
# UI
# =====================================================
st.title("🔥 Scanner robuste — Golden / Death Cross (Polygon)")

tickers = load_tickers()

limit = st.slider("Nombre de tickers", 25, len(tickers), 200)
threshold = st.slider("Distance SMA max (%)", 0.1, 5.0, 1.0, 0.1)

if st.button("🚀 Lancer le scan robuste"):
    send_message("🚀 Scan démarré")

    results = []
    analysed = 0
    detected = 0

    for t in tickers[:limit]:
        analysed += 1

        sma50, _ = get_sma(t, 50)
        time.sleep(SLEEP)

        sma200, sma200_prev = get_sma(t, 200)
        time.sleep(SLEEP)

        price = get_price(t)
        time.sleep(SLEEP)

        if None in (sma50, sma200, sma200_prev, price):
            continue

        dist = (sma50 - sma200) / sma200 * 100
        if abs(dist) > threshold:
            continue

        slope = sma200 - sma200_prev
        golden = sma50 < sma200
        score = compute_score(dist, slope, golden)

        signal = "Golden" if golden else "Death"
        detected += 1

        results.append([
            t, signal, round(price, 2),
            round(sma50, 2), round(sma200, 2),
            round(dist, 2), round(slope, 4), score
        ])

        # -------- batch CSV --------
        if len(results) >= BATCH_SIZE:
            df_batch = pd.DataFrame(
                results,
                columns=["Ticker","Signal","Price","SMA50","SMA200","Distance %","Slope","Score"]
            )
            send_csv(df_batch)
            results.clear()

        # -------- heartbeat --------
        if analysed % HEARTBEAT_EVERY == 0:
            send_message(f"⏳ {analysed}/{limit} analysés — {detected} setups")

    # -------- FIN --------
    if results:
        df_final = pd.DataFrame(
            results,
            columns=["Ticker","Signal","Price","SMA50","SMA200","Distance %","Slope","Score"]
        )
        send_csv(df_final)

    send_message(f"✅ Scan terminé — {analysed} analysés / {detected} setups")

    st.success("Scan terminé avec succès 🔥")
