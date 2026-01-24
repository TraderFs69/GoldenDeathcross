import os
import time
import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ==================================================
# CONFIG STREAMLIT
# ==================================================
st.set_page_config(
    page_title="Russell 3000 – Golden / Death Cross Scanner",
    layout="wide"
)

st.title("📈 Russell 3000 – Golden & Death Cross Scanner (Polygon)")

API_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

# ==================================================
# SIDEBAR
# ==================================================
st.sidebar.header("Configuration")

seuil = st.sidebar.slider(
    "Seuil d'écart (%) pour croisement imminent",
    0.1, 5.0, 1.0, step=0.1
)

ma_type = st.sidebar.selectbox(
    "Type de moyenne mobile",
    ["SMA", "EMA"]
)

send_discord_alerts = st.sidebar.checkbox(
    "📣 Envoyer une alerte Discord groupée",
    value=True
)

# ==================================================
# TICKERS RUSSELL 3000 (EXCEL)
# ==================================================
@st.cache_data
def get_russell3000_tickers():
    file_path = "russell3000_constituents.xlsx"

    if not os.path.exists(file_path):
        st.error("❌ Fichier Russell 3000 introuvable.")
        return []

    df = pd.read_excel(file_path)

    for col in df.columns:
        if col.lower() in ["ticker", "symbol", "tickers", "symbols"]:
            tickers = (
                df[col]
                .astype(str)
                .str.strip()
                .str.upper()
                .str.replace(".", "-", regex=False)
                .dropna()
                .unique()
                .tolist()
            )
            return sorted(tickers)

    st.error("❌ Aucune colonne Ticker/Symbol trouvée.")
    return []

# ==================================================
# POLYGON DATA
# ==================================================
@st.cache_data(ttl=3600)
def get_polygon_data(ticker):
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"2023-01-01/2026-01-01"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={API_KEY}"
    )

    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        return None

    data = r.json()
    if "results" not in data:
        return None

    df = pd.DataFrame(data["results"])
    if df.empty:
        return None

    df["Date"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("Date", inplace=True)

    df.rename(
        columns={
            "o": "Open",
            "h": "High",
            "l": "Low",
            "c": "Close",
            "v": "Volume"
        },
        inplace=True
    )

    return df[["Open", "High", "Low", "Close", "Volume"]]

# ==================================================
# MOYENNES MOBILES
# ==================================================
def calculate_mas(df, ma_type):
    if ma_type == "SMA":
        df["MA50"] = df["Close"].rolling(50).mean()
        df["MA200"] = df["Close"].rolling(200).mean()
    else:
        df["MA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["MA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df

# ==================================================
# DISCORD ALERT GROUPÉE
# ==================================================
def send_grouped_discord_alert(results, ma_type, seuil):
    if not results:
        return

    header = (
        f"📊 **Russell 3000 – Scan terminé**\n"
        f"Type: {ma_type} | Seuil: {seuil}%\n"
        f"Signaux détectés: {len(results)}\n\n"
    )

    lines = []
    for r in results[:25]:  # limite Discord
        lines.append(
            f"**{r['Ticker']}** – {r['Signal']} "
            f"(Écart {r['Écart (%)']}%)"
        )

    message = header + "\n".join(lines)

    if len(results) > 25:
        message += f"\n\n➕ {len(results) - 25} autres signaux non affichés"

    payload = {"content": message}

    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except Exception:
        pass

# ==================================================
# MAIN
# ==================================================
if st.sidebar.button("🚦 Lancer l'analyse"):

    tickers = get_russell3000_tickers()
    if not tickers:
        st.stop()

    detected = []

    progress = st.progress(0)
    total = len(tickers)

    with st.spinner(f"Analyse de {total} actions du Russell 3000..."):

        for i, ticker in enumerate(tickers):

            df = get_polygon_data(ticker)
            if df is None or len(df) < 200:
                progress.progress((i + 1) / total)
                continue

            df = calculate_mas(df, ma_type).dropna()
            if df.empty:
                progress.progress((i + 1) / total)
                continue

            last = df.iloc[-1]
            ma50 = last["MA50"]
            ma200 = last["MA200"]

            if ma200 == 0:
                progress.progress((i + 1) / total)
                continue

            ecart = abs(ma50 - ma200) / ma200 * 100

            if ecart <= seuil:
                signal = (
                    "🟢 Golden Cross imminent"
                    if ma50 < ma200
                    else "🔴 Death Cross imminent"
                )

                detected.append({
                    "Ticker": ticker,
                    "Prix": round(last["Close"], 2),
                    f"{ma_type}50": round(ma50, 2),
                    f"{ma_type}200": round(ma200, 2),
                    "Écart (%)": round(ecart, 2),
                    "Signal": signal
                })

            progress.progress((i + 1) / total)
            time.sleep(0.05)

    # ==================================================
    # DISCORD GROUPÉ
    # ==================================================
    if send_discord_alerts:
        send_grouped_discord_alert(detected, ma_type, seuil)

    # ==================================================
    # AFFICHAGE
    # ==================================================
    if detected:
        df_res = pd.DataFrame(detected).sort_values("Écart (%)")
        st.success(f"{len(df_res)} signaux détectés")
        st.dataframe(df_res, use_container_width=True)

        ticker_choice = st.selectbox(
            "📌 Sélectionne un ticker",
            df_res["Ticker"]
        )

        if ticker_choice:
            df_plot = get_polygon_data(ticker_choice)
            df_plot = calculate_mas(df_plot, ma_type).dropna()

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["Close"], name="Close"))
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["MA50"], name=f"{ma_type}50"))
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["MA200"], name=f"{ma_type}200"))

            fig.update_layout(
                title=f"{ticker_choice} – {ma_type} Cross",
                xaxis_title="Date",
                yaxis_title="Prix"
            )

            st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("Aucun signal détecté avec ce seuil.")

else:
    st.info("👈 Lance le scanner depuis la barre latérale.")
