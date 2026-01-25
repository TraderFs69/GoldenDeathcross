import os
import time
import io
import requests
import streamlit as st
import pandas as pd

# ==================================================
# CONFIG STREAMLIT
# ==================================================
st.set_page_config(
    page_title="SMA Proximity – Top 20",
    layout="wide"
)

st.title("📏 SMA 50 / SMA 200 – Proximité & Pente (Russell 3000)")

API_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

# ==================================================
# SIDEBAR
# ==================================================
st.sidebar.header("Configuration")

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

slope_window = st.sidebar.slider(
    "Fenêtre pente SMA50 (jours)",
    3, 15, 5
)

send_discord = st.sidebar.checkbox(
    "📣 Envoyer Discord + CSV",
    True
)

# ==================================================
# TICKERS – RUSSELL 3000
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
# POLYGON DATA
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
# MOYENNES + PENTE
# ==================================================
def compute_indicators(df):
    if ma_type == "SMA":
        df["MA50"] = df["Close"].rolling(50).mean()
        df["MA200"] = df["Close"].rolling(200).mean()
    else:
        df["MA50"] = df["Close"].ewm(span=50).mean()
        df["MA200"] = df["Close"].ewm(span=200).mean()

    df = df.dropna()

    # pente SMA50 (variation moyenne sur N jours)
    df["Slope_MA50"] = (
        df["MA50"].diff(slope_window) / slope_window
    )

    return df

# ==================================================
# DISCORD
# ==================================================
def send_discord(results):
    df = pd.DataFrame(results)

    csv = io.StringIO()
    df.to_csv(csv, index=False)

    message = (
        f"📏 SMA Proximity – Top 20\n"
        f"Moyennes: {ma_type}\n"
        f"Données: {'Non ajusté' if polygon_adjusted == 'false' else 'Ajusté'}\n"
        f"Résultats envoyés: {len(df)}\n"
        f"CSV joint"
    )

    requests.post(
        DISCORD_WEBHOOK,
        data={"content": message},
        files={"file": ("sma_top20_proximity.csv", csv.getvalue())},
        timeout=15
    )

# ==================================================
# MAIN
# ==================================================
if st.sidebar.button("🚦 Lancer le scan"):

    tickers = get_tickers()
    results = []

    progress = st.progress(0)
    total = len(tickers)

    for i, t in enumerate(tickers):

        df = get_data(t)
        if df is None or len(df) < 210:
            continue

        df = compute_indicators(df)
        last = df.iloc[-1]

        ma50 = last["MA50"]
        ma200 = last["MA200"]

        distance_pct = abs(ma50 - ma200) / ma200 * 100
        slope = last["Slope_MA50"]

        biais = (
            "Haussier" if ma50 < ma200 else "Baissier"
        )

        results.append({
            "Ticker": t,
            "Prix": round(last["Close"], 2),
            "MA50": round(ma50, 2),
            "MA200": round(ma200, 2),
            "Distance %": round(distance_pct, 3),
            "Pente SMA50": round(slope, 4),
            "Biais": biais
        })

        progress.progress((i + 1) / total)
        time.sleep(0.015)

    # =============================
    # TOP 20 PLUS PROCHES
    # =============================
    df_res = (
        pd.DataFrame(results)
        .sort_values("Distance %")
        .head(20)
    )

    if send_discord:
        send_discord(df_res)

    if not df_res.empty:
        st.success("Top 20 des SMA 50 / 200 les plus proches")
        st.dataframe(df_res, use_container_width=True)
    else:
        st.warning("Aucun résultat calculé.")

else:
    st.info("👈 Lance le scan depuis la barre latérale.")
