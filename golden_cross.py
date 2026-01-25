import os
import time
import io
import requests
import streamlit as st
import pandas as pd

# ==================================================
# CONFIG
# ==================================================
st.set_page_config(page_title="Anticipation Cross Scanner", layout="wide")
st.title("📈 Anticipation Golden / Death Cross – Russell 3000")

API_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

# ==================================================
# SIDEBAR
# ==================================================
seuil = st.sidebar.slider("Seuil écart (%)", 0.1, 5.0, 1.0, 0.1)
window_no_cross = st.sidebar.slider("Fenêtre sans cross (jours)", 5, 60, 20)
ma_type = st.sidebar.selectbox("Type de moyenne", ["SMA", "EMA"])

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
    results = []
    progress = st.progress(0)

    for i, t in enumerate(tickers):
        df = get_data(t)
        if df is None or len(df) < 200 + window_no_cross:
            continue

        df = compute_ma(df)

        # diff = MA50 - MA200
        df["diff"] = df["MA50"] - df["MA200"]

        # ---- CONDITION CLÉ : PAS DE CROSS PASSÉ ----
        recent_diff = df["diff"].iloc[-window_no_cross:]
        if recent_diff.gt(0).any() and recent_diff.lt(0).any():
            continue  # changement de signe = cross passé

        last = df.iloc[-1]
        prev = df.iloc[-2]

        diff_today = last["diff"]
        diff_prev = prev["diff"]

        ecart_pct = abs(diff_today) / last["MA200"] * 100
        if ecart_pct > seuil:
            continue

        # convergence réelle
        if abs(diff_today) >= abs(diff_prev):
            continue

        # SIGNAL
        if diff_today < 0:
            signal = "🟢 Golden Cross POTENTIEL"
        else:
            signal = "🔴 Death Cross POTENTIEL"

        vitesse = abs(diff_prev) - abs(diff_today)
        jours_estimes = round(abs(diff_today) / vitesse, 1) if vitesse > 0 else None
        score = round((1 / ecart_pct) * vitesse * 50, 1)

        results.append({
            "Ticker": t,
            "Prix": round(last["Close"], 2),
            "MA50": round(last["MA50"], 2),
            "MA200": round(last["MA200"], 2),
            "Écart %": round(ecart_pct, 3),
            "Vitesse": round(vitesse, 4),
            "Jours estimés": jours_estimes,
            "Score": score,
            "Signal": signal
        })

        progress.progress((i + 1) / len(tickers))
        time.sleep(0.03)

    if send_discord:
        send_discord(results)

    if results:
        df_res = pd.DataFrame(results).sort_values("Score", ascending=False)
        st.success(f"{len(df_res)} signaux anticipés (AUCUN cross passé)")
        st.dataframe(df_res, use_container_width=True)
    else:
        st.warning("Aucun signal anticipé détecté.")
