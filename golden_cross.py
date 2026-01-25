import time
import io
import requests
import streamlit as st
import pandas as pd

# ==================================================
# CONFIG STREAMLIT
# ==================================================
st.set_page_config(
    page_title="Price vs SMA Scanner",
    layout="wide"
)

st.title("📏 Distance du PRIX vs SMA 50 & SMA 200 (Russell 3000)")

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

top_n = st.sidebar.slider(
    "Top N plus proches",
    5, 50, 20
)

reference_ma = st.sidebar.radio(
    "Référence de proximité",
    ["SMA50", "SMA200"]
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
# MOYENNES
# ==================================================
def compute_ma(df):
    if ma_type == "SMA":
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
    else:
        df["SMA50"] = df["Close"].ewm(span=50).mean()
        df["SMA200"] = df["Close"].ewm(span=200).mean()

    return df.dropna()

# ==================================================
# DISCORD
# ==================================================
def send_discord(df):
    csv = io.StringIO()
    df.to_csv(csv, index=False)

    message = (
        f"📏 Price vs SMA Scan\n"
        f"Top {len(df)} – Référence {reference_ma}\n"
        f"Moyennes: {ma_type}\n"
        f"Données: {'Non ajusté' if polygon_adjusted == 'false' else 'Ajusté'}"
    )

    requests.post(
        DISCORD_WEBHOOK,
        data={"content": message},
        files={"file": ("price_vs_sma.csv", csv.getvalue())},
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

        close = last["Close"]
        sma50 = last["SMA50"]
        sma200 = last["SMA200"]

        dist_50 = (close - sma50) / sma50 * 100
        dist_200 = (close - sma200) / sma200 * 100

        results.append({
            "Ticker": t,
            "Close": round(close, 2),
            "SMA50": round(sma50, 2),
            "SMA200": round(sma200, 2),
            "Dist Close → SMA50 (%)": round(dist_50, 3),
            "Dist Close → SMA200 (%)": round(dist_200, 3)
        })

        progress.progress((i + 1) / len(tickers))
        time.sleep(0.01)

    df_res = pd.DataFrame(results)

    if reference_ma == "SMA50":
        df_res = df_res.sort_values(
            "Dist Close → SMA50 (%)",
            key=lambda x: x.abs()
        )
    else:
        df_res = df_res.sort_values(
            "Dist Close → SMA200 (%)",
            key=lambda x: x.abs()
        )

    df_res = df_res.head(top_n)

    if send_discord:
        send_discord(df_res)

    st.success(f"Top {top_n} – distance du PRIX vs {reference_ma}")
    st.dataframe(df_res, use_container_width=True)

else:
    st.info("👈 Lance le scan depuis la barre latérale.")
