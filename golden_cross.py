import os
import re
import requests
import time

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ==============================
# CONFIG STREAMLIT
# ==============================
st.set_page_config(
    page_title="S&P 500 Golden / Death Cross Scanner",
    layout="wide"
)

st.title("📈 Scanner S&P 500 – Golden & Death Cross (Polygon)")

API_KEY = st.secrets["POLYGON_API_KEY"]

# ==============================
# SIDEBAR
# ==============================
st.sidebar.header("Configuration")

seuil = st.sidebar.slider(
    "Seuil d'écart (%) pour croisement imminent",
    0.1, 5.0, 1.0, step=0.1
)

ma_type = st.sidebar.selectbox(
    "Type de moyenne mobile",
    ["SMA", "EMA"]
)

max_tickers = st.sidebar.number_input(
    "Nombre max de tickers analysés",
    min_value=20,
    max_value=500,
    value=150,
    step=10
)

# ==============================
# S&P 500 TICKERS
# ==============================
@st.cache_data
def get_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = pd.read_html(url)
    df = tables[0]
    symbols = df["Symbol"].astype(str).str.replace(".", "-", regex=False)
    return sorted(symbols.tolist())

# ==============================
# POLYGON DATA
# ==============================
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
            "c": "Close",
            "o": "Open",
            "h": "High",
            "l": "Low",
            "v": "Volume"
        },
        inplace=True
    )

    return df[["Open", "High", "Low", "Close", "Volume"]]

# ==============================
# CALCUL DES MOYENNES
# ==============================
def calculate_mas(df, ma_type):
    if ma_type == "SMA":
        df["MA50"] = df["Close"].rolling(50).mean()
        df["MA200"] = df["Close"].rolling(200).mean()
    else:
        df["MA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["MA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df

# ==============================
# MAIN
# ==============================
if st.sidebar.button("🚦 Lancer l'analyse"):

    tickers = get_sp500_tickers()[:int(max_tickers)]
    detected = []

    with st.spinner(f"Analyse de {len(tickers)} tickers via Polygon..."):

        for ticker in tickers:
            df = get_polygon_data(ticker)

            if df is None or len(df) < 200:
                continue

            df = calculate_mas(df, ma_type)
            df = df.dropna()

            if df.empty:
                continue

            last = df.iloc[-1]
            ma50 = last["MA50"]
            ma200 = last["MA200"]

            if ma200 == 0:
                continue

            ecart = abs(ma50 - ma200) / ma200 * 100

            if ecart <= seuil:
                signal = (
                    "Golden Cross imminent"
                    if ma50 < ma200
                    else "Death Cross imminent"
                )

                detected.append({
                    "Ticker": ticker,
                    "Prix": round(last["Close"], 2),
                    f"{ma_type}50": round(ma50, 2),
                    f"{ma_type}200": round(ma200, 2),
                    "Écart (%)": round(ecart, 2),
                    "Signal": signal
                })

            time.sleep(0.05)  # anti-rate-limit Polygon

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
    st.info("👈 Configure et lance l’analyse depuis la barre latérale.")
