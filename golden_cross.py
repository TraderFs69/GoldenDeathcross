import streamlit as st
import pandas as pd
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(layout="wide")

POLYGON_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

LOOKBACK = 260                 # ~1 an de données daily
SLEEP_BETWEEN_CALLS = 0.15     # 150 ms = safe Polygon Starter

# =====================================================
# SESSION HTTP ROBUSTE (ANTI TIMEOUT)
# =====================================================
def build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

SESSION = build_session()

# =====================================================
# LOAD TICKERS (RUSSELL 3000 — COLONNE A = Symbol)
# =====================================================
@st.cache_data
def load_tickers():
    df = pd.read_excel("russell3000_constituents.xlsx", header=0)
    tickers = (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
    )
    return [t for t in tickers if t != "SYMBOL"]

TICKERS = load_tickers()

# =====================================================
# POLYGON — AGGS DAILY (ROBUSTE)
# =====================================================
@st.cache_data(ttl=3600)
def get_data(ticker):
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{LOOKBACK}/2025-01-01"
        f"?adjusted=true&sort=asc&apiKey={POLYGON_KEY}"
    )
    try:
        r = SESSION.get(url, timeout=10)
        if r.status_code != 200 or not r.text or r.text[0] != "{":
            return None

        data = r.json()
        if "results" not in data or not data["results"]:
            return None

        df = pd.DataFrame(data["results"])
        df["Close"] = df["c"]
        return df

    except requests.exceptions.ReadTimeout:
        return None
    except Exception:
        return None

# =====================================================
# STRATÉGIE — GOLDEN / DEATH CROSS
# =====================================================
def detect_cross(df):
    if len(df) < 200:
        return None

    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["EMA200"] = df["Close"].ewm(span=200).mean()

    prev = df.iloc[-2]
    last = df.iloc[-1]

    if prev["EMA50"] < prev["EMA200"] and last["EMA50"] > last["EMA200"]:
        return "🟢 Golden Cross"

    if prev["EMA50"] > prev["EMA200"] and last["EMA50"] < last["EMA200"]:
        return "🔴 Death Cross"

    return None

# =====================================================
# DISCORD — ENVOI WEBHOOK
# =====================================================
def send_to_discord(rows):
    if not DISCORD_WEBHOOK or not rows:
        return

    lines = []
    for ticker, signal in rows:
        lines.append(f"{signal} **{ticker}**")

    message = (
        "🚨 **Golden / Death Cross détecté**\n\n"
        + "\n".join(lines[:25])
    )

    payload = {"content": message[:1900]}

    try:
        SESSION.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except Exception:
        pass

# =====================================================
# UI
# =====================================================
st.title("📈 Golden / Death Cross — Polygon (Version Stable + Discord)")

limit = st.slider(
    "Nombre de tickers à analyser",
    min_value=50,
    max_value=len(TICKERS),
    value=300
)

if st.button("🚀 Scanner et envoyer sur Discord"):
    rows = []

    with st.spinner("Scan en cours…"):
        for t in TICKERS[:limit]:
            df = get_data(t)
            time.sleep(SLEEP_BETWEEN_CALLS)   # ⬅️ protection API

            if df is None:
                continue

            signal = detect_cross(df)
            if signal:
                rows.append([t, signal])

    if rows:
        result = pd.DataFrame(rows, columns=["Ticker", "Signal"])
        st.dataframe(result, width="stretch")

        send_to_discord(rows)   # ⬅️ ENVOI DISCORD

        st.success(f"{len(rows)} signaux détectés et envoyés sur Discord ✅")
    else:
        st.info("Aucun signal détecté.")
