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

SLEEP_BETWEEN_CALLS = 0.2   # IMPORTANT : 2 SMA / ticker (Starter safe)

# =====================================================
# SESSION HTTP ROBUSTE
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
# POLYGON — SMA OFFICIELLES
# =====================================================
@st.cache_data(ttl=900)
def get_polygon_sma(ticker, window):
    url = (
        f"https://api.polygon.io/v1/indicators/sma/{ticker}"
        f"?timespan=day"
        f"&window={window}"
        f"&series_type=close"
        f"&adjusted=true"
        f"&order=desc"
        f"&limit=1"
        f"&apiKey={POLYGON_KEY}"
    )

    try:
        r = SESSION.get(url, timeout=10)
        if r.status_code != 200:
            return None

        data = r.json()
        values = data.get("results", {}).get("values", [])
        if not values:
            return None

        return round(values[0]["value"], 2)

    except Exception:
        return None

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
        "📊 **SMA 50 / SMA 200 — Proximité de cross (Polygon Indicators)**\n\n"
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
st.title("📊 SMA 50 / SMA 200 — Distance ACTUELLE (Polygon Indicators)")

limit = st.slider(
    "Nombre de tickers à analyser",
    min_value=25,
    max_value=len(TICKERS),
    value=150
)

threshold = st.slider(
    "Distance max (%) pour alerte Discord",
    0.1, 5.0, 1.0, 0.1
)

if st.button("🚀 Scanner et envoyer sur Discord"):
    rows = []

    with st.spinner("Scan en cours…"):
        for t in TICKERS[:limit]:
            sma50 = get_polygon_sma(t, 50)
            time.sleep(SLEEP_BETWEEN_CALLS)

            sma200 = get_polygon_sma(t, 200)
            time.sleep(SLEEP_BETWEEN_CALLS)

            if sma50 is None or sma200 is None:
                continue

            distance_pct = round((sma50 - sma200) / sma200 * 100, 2)

            if abs(distance_pct) > threshold:
                continue

            if sma50 < sma200:
                bias = "🟡 Golden Cross POTENTIEL"
            else:
                bias = "🔴 Death Cross POTENTIEL"

            rows.append([
                t,
                bias,
                sma50,
                sma200,
                distance_pct
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
