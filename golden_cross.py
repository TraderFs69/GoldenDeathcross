import os
import time
import io
import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ==================================================
# CONFIG STREAMLIT
# ==================================================
st.set_page_config(page_title="Anticipation Golden / Death Cross", layout="wide")
st.title("📈 Anticipation Golden / Death Cross – Russell 3000")

API_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

# ==================================================
# SIDEBAR
# ==================================================
st.sidebar.header("Configuration")

seuil = st.sidebar.slider("Seuil écart SMA (%)", 0.1, 5.0, 1.0, 0.1)
jours_exclusion = st.sidebar.slider("Exclure crosses < X jours", 5, 60, 20)
ma_type = st.sidebar.selectbox("Type de moyenne", ["SMA", "EMA"])

price_adjustment = st.sidebar.radio(
    "Données de prix",
    ["Non ajusté (TradingView)", "Ajusté (splits + dividendes)"],
    index=0
)

polygon_adjusted = "true" if "Ajusté" in price_adjustment else "false"

send_discord_alerts = st.sidebar.checkbox("📣 Alerte Discord + CSV", True)

# ==================================================
# TICKERS
# ==================================================
@st.cache_data
def get_tickers():
    df = pd.read_excel("russell3000_constituents.xlsx")
    for col in df.columns:
        if col.lower() in ["ticker", "symbol"]:
            return (
                df[col].astype(str)
                .str.upper()
                .str.replace(".", "-", regex=False)
                .dropna()
                .unique()
                .tolist()
            )
    return []

# ==================================================
# POLYGON
# ==================================================
@st.cache_data(ttl=3600)
def get_data(ticker):
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"2023-01-01/2026-01-01"
        f"?adjusted={polygon_adjusted}&sort=asc&limit=50000&apiKey={API_KEY}"
    )
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json().get("results")
    if not data:
        return None
    df = pd.DataFrame(data)
    df["Date"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("Date", inplace=True)
    df.rename(columns={"c": "Close"}, inplace=True)
    return df[["Close"]]

# ==================================================
# MOYENNES
# ==================================================
def compute_ma(df):
    if ma_type == "SMA":
        df["MA50"] = df["Close"].rolling(50).mean()
        df["MA200"] = df["Close"].rolling(200).mean()
    else:
        df["MA50"] = df["Close"].ewm(span=50).mean()
        df["MA200"] = df["Close"].ewm(span=200).mean()
    return df.dropna()

# ==================================================
# DISCORD
# ==================================================
def send_discord(results):
    if not results:
        return
    df = pd.DataFrame(results)
    csv = io.StringIO()
    df.to_csv(csv, index=False)
    payload = {
        "content": f"📊 Scan anticipation terminé\nSignaux: {len(df)}\nCSV joint"
    }
    requests.post(
        DISCORD_WEBHOOK,
        data=payload,
        files={"file": ("anticipation_cross.csv", csv.getvalue())},
        timeout=15
    )

# ==================================================
# MAIN
# ==================================================
if st.sidebar.button("🚦 Lancer le scan"):

    tickers = get_tickers()
    progress = st.progress(0)
    results = []

    for i, t in enumerate(tickers):
        df = get_data(t)
        if df is None or len(df) < 220:
            continue

        df = compute_ma(df)

        # Exclusion cross récent
        cross_recent = (
            (df["MA50"] - df["MA200"]).abs().rolling(jours_exclusion).min().iloc[-1] < 1e-6
        )
        if cross_recent:
            continue

        last, prev = df.iloc[-1], df.iloc[-2]

        ma50, ma200 = last["MA50"], last["MA200"]
        ma50_p, ma200_p = prev["MA50"], prev["MA200"]

        ecart = abs(ma50 - ma200) / ma200 * 100
        ecart_prev = abs(ma50_p - ma200_p) / ma200_p * 100
        vitesse = ecart_prev - ecart

        if ecart > seuil or vitesse <= 0:
            continue

        # Signal
        if ma50 < ma200 and ma50_p < ma200_p:
            signal = "🟢 Golden Cross imminent"
        elif ma50 > ma200 and ma50_p > ma200_p:
            signal = "🔴 Death Cross imminent"
        else:
            continue

        jours_estimes = round(ecart / vitesse, 1) if vitesse > 0 else None
        score = min(100, round((1 / ecart) * vitesse * 50, 1))

        results.append({
            "Ticker": t,
            "Prix": round(last["Close"], 2),
            "MA50": round(ma50, 2),
            "MA200": round(ma200, 2),
            "Écart %": round(ecart, 3),
            "Vitesse": round(vitesse, 3),
            "Jours estimés": jours_estimes,
            "Score": score,
            "Signal": signal
        })

        progress.progress((i + 1) / len(tickers))
        time.sleep(0.03)

    if send_discord_alerts:
        send_discord(results)

    if results:
        df_res = pd.DataFrame(results).sort_values("Score", ascending=False)
        st.success(f"{len(df_res)} signaux anticipés")
        st.dataframe(df_res, use_container_width=True)
    else:
        st.warning("Aucun signal anticipé détecté.")
