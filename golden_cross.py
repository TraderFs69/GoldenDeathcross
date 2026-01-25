import time
import io
import requests
import streamlit as st
import pandas as pd

# ==================================================
# CONFIG STREAMLIT
# ==================================================
st.set_page_config(
    page_title="SMA50 vs SMA200 – Dernier close",
    layout="wide"
)

st.title("📐 SMA50 & SMA200 AU DERNIER CLOSE (pas au croisement)")

API_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

# ==================================================
# SIDEBAR
# ==================================================
ma_type = st.sidebar.selectbox("Type de moyenne", ["SMA", "EMA"])
send_discord = st.sidebar.checkbox("📣 Envoyer Discord + CSV", True)

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
# POLYGON DATA
# ==================================================
@st.cache_data(ttl=3600)
def get_data(ticker):
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"2022-01-01/2026-01-01"
        f"?adjusted=false&sort=asc&limit=50000&apiKey={API_KEY}"
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
# MOYENNES (SANS dropna)
# ==================================================
def compute_ma(df):
    if ma_type == "SMA":
        df["SMA50"] = df["Close"].rolling(50, min_periods=50).mean()
        df["SMA200"] = df["Close"].rolling(200, min_periods=200).mean()
    else:
        df["SMA50"] = df["Close"].ewm(span=50, min_periods=50).mean()
        df["SMA200"] = df["Close"].ewm(span=200, min_periods=200).mean()

    return df

# ==================================================
# DISCORD
# ==================================================
def send_discord(df):
    csv = io.StringIO()
    df.to_csv(csv, index=False)

    message = (
        f"📐 SMA50 vs SMA200 – DERNIER CLOSE\n"
        f"(Diff < 0 → Golden possible | Diff > 0 → Death possible)\n"
        f"Résultats: {len(df)}"
    )

    requests.post(
        DISCORD_WEBHOOK,
        data={"content": message},
        files={"file": ("sma_last_close.csv", csv.getvalue())},
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

        # 🔴 ON PREND EXPLICITEMENT LE DERNIER CLOSE
        last = df.iloc[-1]

        # sécurité
        if pd.isna(last["SMA50"]) or pd.isna(last["SMA200"]):
            continue

        sma50 = last["SMA50"]
        sma200 = last["SMA200"]

        diff = sma50 - sma200
        diff_pct = diff / sma200 * 100

        results.append({
            "Ticker": t,
            "SMA50": round(sma50, 2),
            "SMA200": round(sma200, 2),
            "Diff SMA50 − SMA200": round(diff, 4),
            "Diff %": round(diff_pct, 3),
            "Lecture": (
                "Golden Cross possible"
                if diff < 0
                else "Death Cross possible"
            )
        })

        progress.progress((i + 1) / len(tickers))
        time.sleep(0.005)

    df_res = (
        pd.DataFrame(results)
        .sort_values("Diff %", key=lambda x: x.abs())
        .head(20)
    )

    if send_discord:
        send_discord(df_res)

    st.success("Top 20 – SMA50 la plus proche de SMA200 (AUJOURD’HUI)")
    st.dataframe(df_res, use_container_width=True)

else:
    st.info("👈 Lance le scan depuis la barre latérale.")
