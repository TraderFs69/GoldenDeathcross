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

SLEEP_BETWEEN_CALLS = 0.25  # safe Polygon Starter

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
# LOAD TICKERS
# =====================================================
@st.cache_data
def load_tickers():
    df = pd.read_excel("russell3000_constituents.xlsx")
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
# POLYGON INDICATORS
# =====================================================
@st.cache_data(ttl=900)
def get_polygon_sma(ticker, window):
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
def get_last_price(ticker):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_KEY}"
    try:
        r = SESSION.get(url, timeout=10).json()
        return r["results"][0]["c"]
    except:
        return None

# =====================================================
# SCORE
# =====================================================
def compute_score(distance_pct, slope, is_golden):
    score = 0
    score += max(0, 40 - abs(distance_pct) * 10)
    score += min(30, abs(slope) * 200)
    if is_golden:
        score += 20
    return round(min(100, max(0, score)), 1)

# =====================================================
# DISCORD — TEXTE
# =====================================================
def send_message_to_discord(message: str):
    payload = {"content": message[:1900]}
    r = SESSION.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    st.write("Discord TEXT status:", r.status_code)

# =====================================================
# DISCORD — CSV
# =====================================================
def send_csv_to_discord(df: pd.DataFrame):
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    files = {
        "file": ("cross_scanner.csv", csv_buffer.getvalue(), "text/csv")
    }

    r = SESSION.post(DISCORD_WEBHOOK, files=files, timeout=15)
    st.write("Discord CSV status:", r.status_code)

# =====================================================
# UI
# =====================================================
st.title("📊 Golden / Death Cross — Projection & Score (Polygon)")

limit = st.slider("Nombre de tickers analysés", 25, len(TICKERS), 150)
threshold = st.slider("Distance max SMA (%)", 0.1, 5.0, 1.0, 0.1)

# -------- TEST DISCORD --------
if st.button("🧪 Test Discord"):
    send_message_to_discord("🧪 Test Discord — webhook OK")

# -------- SCAN --------
if st.button("🚀 Scanner & envoyer sur Discord"):
    rows = []

    with st.spinner("Scan en cours…"):
        for t in TICKERS[:limit]:
            sma50_now, _ = get_polygon_sma(t, 50)
            time.sleep(SLEEP_BETWEEN_CALLS)

            sma200_now, sma200_prev = get_polygon_sma(t, 200)
            time.sleep(SLEEP_BETWEEN_CALLS)

            price = get_last_price(t)
            time.sleep(SLEEP_BETWEEN_CALLS)

            if None in (sma50_now, sma200_now, sma200_prev, price):
                continue

            distance_pct = (sma50_now - sma200_now) / sma200_now * 100
            if abs(distance_pct) > threshold:
                continue

            slope = sma200_now - sma200_prev
            days_to_cross = abs((sma50_now - sma200_now) / slope) if slope != 0 else None

            is_golden = sma50_now < sma200_now
            signal = "🟢 Golden Cross POTENTIEL" if is_golden else "🔴 Death Cross POTENTIEL"

            score = compute_score(distance_pct, slope, is_golden)

            rows.append([
                t,
                signal,
                round(price, 2),
                round(sma50_now, 2),
                round(sma200_now, 2),
                round(distance_pct, 2),
                round(slope, 4),
                round(days_to_cross, 1) if days_to_cross else None,
                score
            ])

    if rows:
        df = pd.DataFrame(
            rows,
            columns=[
                "Ticker", "Signal", "Price",
                "SMA50", "SMA200",
                "Distance (%)", "Slope SMA200",
                "Jours estimés avant cross", "Score"
            ]
        ).sort_values("Score", ascending=False)

        st.dataframe(df, width="stretch")

        # -------- MESSAGE --------
        lines = []
        for _, r in df.head(10).iterrows():
            icon = "🟢" if "Golden" in r["Signal"] else "🔴"
            lines.append(
                f"{icon} **{r['Ticker']}** | {r['Price']}$ | Δ {r['Distance (%)']}% | Score {r['Score']}"
            )

        message = (
            "📊 **Golden / Death Cross — Projection & Probabilité**\n\n"
            + "\n".join(lines)
        )

        send_message_to_discord(message)
        time.sleep(1)  # ⬅️ IMPORTANT
        send_csv_to_discord(df)

        st.success(f"{len(df)} setups envoyés sur Discord ✅")
    else:
        st.info("Aucun setup valide avec les critères actuels.")
