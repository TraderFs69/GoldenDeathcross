import streamlit as st
import pandas as pd
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =====================================================
# CONFIG GÉNÉRALE
# =====================================================
st.set_page_config(layout="wide")

POLYGON_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

LOOKBACK = 350                 # IMPORTANT : match TradingView (SMA200)
SLEEP_BETWEEN_CALLS = 0.15     # Safe pour Polygon Starter

# =====================================================
# SESSION HTTP ROBUSTE (Polygon + Discord)
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
# LOAD TICKERS (COLONNE A = Symbol)
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
# POLYGON — AGGS DAILY (PRIX AJUSTÉS)
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
        df["Close"] = df["c"]   # close AJUSTÉ (match TradingView)
        return df

    except Exception:
        return None

# =====================================================
# LOGIQUE SMA — DISTANCE ACTUELLE (PAS DE CROSS PASSÉ)
# =====================================================
def sma_proximity(df):
    if len(df) < 200:
        return None

    # SMA STRICTES (match TradingView)
    df["SMA50"] = df["Close"].rolling(window=50, min_periods=50).mean()
    df["SMA200"] = df["Close"].rolling(window=200, min_periods=200).mean()

    last = df.iloc[-1]  # dernière bougie clôturée (daily)

    sma50 = last["SMA50"]
    sma200 = last["SMA200"]

    if pd.isna(sma50) or pd.isna(sma200):
        return None

    distance_pct = round((sma50 - sma200) / sma200 * 100, 2)

    if sma50 < sma200:
        bias = "🟡 Golden Cross POTENTIEL"
    else:
        bias = "🔴 Death Cross POTENTIEL"

    return {
        "Bias": bias,
        "SMA50": round(sma50, 2),
        "SMA200": round(sma200, 2),
        "Distance (%)": distance_pct
    }

# =====================================================
# DISCORD — ENVOI WEBHOOK
# =====================================================
def send_to_discord(rows):
    if not DISCORD_WEBHOOK or not rows:
        return

    lines = []
    for r in rows[:25]:
        lines.append(
            f"{r[1]} **{r[0]}** | SMA50 {r[2]} | SMA200 {r[3]} | Δ {r[4]}%"
        )

    message = (
        "📊 **SMA 50 / SMA 200 — Proximité de cross (prix ajustés)**\n\n"
        + "\n".join(lines)
    )

    payload = {"content": message[:1900]}

    try:
        SESSION.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except Exception:
        pass

# =====================================================
# UI STREAMLIT
# =====================================================
st.title("📊 SMA 50 / SMA 200 — Distance ACTUELLE (aligné TradingView)")

limit = st.slider(
    "Nombre de tickers à analyser",
    min_value=50,
    max_value=len(TICKERS),
    value=300
)

threshold = st.slider(
    "Distance max (%) pour alerte Discord",
    0.1, 5.0, 1.0, 0.1
)

if st.button("🚀 Scanner et envoyer sur Discord"):
    rows = []

    with st.spinner("Scan en cours…"):
        for t in TICKERS[:limit]:
            df = get_data(t)
            time.sleep(SLEEP_BETWEEN_CALLS)

            if df is None:
                continue

            info = sma_proximity(df)
            if info and abs(info["Distance (%)"]) <= threshold:
                rows.append([
                    t,
                    info["Bias"],
                    info["SMA50"],
                    info["SMA200"],
                    info["Distance (%)"]
                ])

    if rows:
        result = (
            pd.DataFrame(
                rows,
                columns=["Ticker", "Signal", "SMA50", "SMA200", "Distance (%)"]
            )
            .sort_values("Distance (%)", key=lambda x: abs(x))
        )

        st.dataframe(result, width="stretch")
        send_to_discord(rows)

        st.success(
            f"{len(rows)} tickers proches d’un cross potentiel envoyés sur Discord ✅"
        )
    else:
        st.info("Aucun ticker proche d’un cross avec les critères actuels.")
