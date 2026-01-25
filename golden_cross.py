import os
import time
import io
import requests
import streamlit as st
import pandas as pd

# ==================================================
# CONFIG
# ==================================================
st.set_page_config(page_title="SMA Proximity Scanner", layout="wide")
st.title("📏 SMA 50 / SMA 200 – Scanner de proximité (Russell 3000)")

API_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

# ==================================================
# SIDEBAR
# ==================================================
st.sidebar.header("Configuration")

seuil = st.sidebar.slider(
    "Distance max entre SMA50 et SMA200 (%)",
    0.1, 5.0, 1.0, 0.1
)

ma_type = st.sidebar.selectbox(
    "Type de moyenne",
    ["SMA", "EMA"]
)

price_adjustment = st.sidebar.radio(
    "Données de prix",
    ["Non ajusté (TradingView)", "Ajusté (splits + dividendes)"],
    index=0
)

polygon_adjusted = "true" if "Ajusté" in price_adjustment else "false"

send_discord = st.sidebar.checkbox("📣 Discord + CSV", True)

# ==================================================
# TICKERS
# ==================================================
@st.cache_data
def get_tickers():
    df = pd.read_excel("russell3000_constituents.xlsx")
    for col in df.columns:
        if col.lower() in ["ticker", "symbol"]:
            return (
                df[col]
                .astype(str)
                .str.upper()
                .str.replace(".", "-", regex=False)
                .dropna()
                .unique()
                .tolist()
            )
    return []

# ==================================================
# DATA
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
        "content": (
            f"📏 SMA Proximity Scan terminé\n"
            f"Seuil: {seuil}%\n"
            f"Résultats: {len(df)}\n"
            f"CSV joint"
        )
    }

    requests.post(
        DISCORD_WEBHOOK,
        data=payload,
        files={"file": ("sma_proximity.csv", csv.getvalue())},
        timeout=15
    )

# ==================================================
# MAIN
# ==================================================
if st.sidebar.button("🚦 Lancer le scan"):

    tickers = get_tickers()
    results = []
    progress = st.progress(0)

    for i, t in enumerate(tickers):

        df = get_data(t)
        if df is None or len(df) < 200:
            continue

        df = compute_ma(df)
        last = df.iloc[-1]

        ma50 = last["MA50"]
        ma200 = last["MA200"]

        distance_pct = abs(ma50 - ma200) / ma200 * 100

        if distance_pct <= seuil:
            biais = (
                "Biais haussier (SMA50 < SMA200)"
                if ma50 < ma200
                else "Biais baissier (SMA50 > SMA200)"
            )

            results.append({
                "Ticker": t,
                "Prix": round(last["Close"], 2),
                "MA50": round(ma50, 2),
                "MA200": round(ma200, 2),
                "Distance %": round(distance_pct, 3),
                "Biais": biais
            })

        progress.progress((i + 1) / len(tickers))
        time.sleep(0.02)

    if send_discord:
        send_discord(results)

    if results:
        df_res = pd.DataFrame(results).sort_values("Distance %")
        st.success(f"{len(df_res)} actions avec SMA proches")
        st.dataframe(df_res, use_container_width=True)
    else:
        st.warning("Aucune action avec SMA proches selon ce seuil.")
