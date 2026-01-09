import os
import re
import requests

import streamlit as st 
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

# ==============================
# Config Streamlit
# ==============================
st.set_page_config(page_title="S&P 500 Golden/Death Cross Scanner", layout="wide")
st.title("📈 Scanner S&P 500 : Golden & Death Cross (SMA/EMA)")

st.sidebar.header("Configuration")
seuil = st.sidebar.slider(
    "Seuil d'écart (%) pour signaler un croisement imminent",
    0.1, 5.0, 1.0, step=0.1
)
ma_type = st.sidebar.selectbox("Type de moyenne mobile :", ["SMA", "EMA"])

# ==============================
# Récupération S&P 500 (robuste)
# ==============================
@st.cache_data
def get_sp500_tickers():
    """
    Renvoie la liste des tickers S&P 500 au format Yahoo (BRK.B -> BRK-B).
    Ordre de priorité :
      1) Fichier local sp500_constituents.xlsx ou sp500_constituents.csv
      2) Wikipedia (2 URLs)
      3) Slickcharts (fallback)
    """
    # ---------------------------------------------------------------
    # 1) Fichiers locaux
    # ---------------------------------------------------------------
    local_files = ["sp500_constituents.xlsx", "sp500_constituents.csv"]

    for path in local_files:
        if os.path.exists(path):
            try:
                if path.endswith(".xlsx"):
                    df = pd.read_excel(path)
                else:
                    df = pd.read_csv(path)

                if "Symbol" not in df.columns:
                    st.warning(f"Fichier {path} trouvé mais sans colonne 'Symbol'. Ignoré.")
                    continue

                symbols = (
                    df["Symbol"]
                    .astype(str)
                    .str.strip()
                    .dropna()
                    .tolist()
                )

                # Format Yahoo
                symbols = [s.replace(".", "-") for s in symbols]
                symbols = sorted(set([s for s in symbols if s]))

                st.info(f"S&P 500 chargé depuis {path} ({len(symbols)} tickers).")
                return symbols

            except Exception as e:
                st.warning(f"Erreur lors de la lecture de {path} : {e}")
                continue

    # ---------------------------------------------------------------
    # 2) Wikipedia (2 URL, parsing robuste)
    # ---------------------------------------------------------------
    wiki_urls = [
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies?action=render",
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://en.wikipedia.org/",
    }

    def extract_symbols(tables):
        """Cherche une colonne contenant 'Symbol'."""
        for df in tables:
            for col in df.columns:
                if re.search(r"symbol", str(col), re.I):
                    syms = (
                        df[col]
                        .astype(str)
                        .str.strip()
                        .dropna()
                        .tolist()
                    )
                    return syms
        return None

    for url in wiki_urls:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            tables = pd.read_html(r.text)

            symbols = extract_symbols(tables)
            if symbols:
                symbols = [s.replace(".", "-") for s in symbols]
                symbols = sorted(set([s for s in symbols if s]))
                st.info(f"S&P 500 chargé depuis Wikipedia ({len(symbols)} tickers).")
                return symbols

        except Exception as e:
            st.warning(f"Wikipedia en échec ({url}) : {e}")

    # ---------------------------------------------------------------
    # 3) Slickcharts (fallback)
    # ---------------------------------------------------------------
    try:
        sc = requests.get("https://www.slickcharts.com/sp500", headers=headers, timeout=20)
        sc.raise_for_status()
        tables = pd.read_html(sc.text)

        for df in tables:
            if "Symbol" in df.columns:
                symbols = (
                    df["Symbol"]
                    .astype(str)
                    .str.strip()
                    .dropna()
                    .tolist()
                )
                symbols = [s.replace(".", "-") for s in symbols]
                symbols = sorted(set(symbols))
                st.info(f"S&P 500 chargé depuis Slickcharts ({len(symbols)} tickers).")
                return symbols

    except Exception as e:
        st.error(f"Erreur Slickcharts : {e}")

    # ---------------------------------------------------------------
    # Rien trouvé
    # ---------------------------------------------------------------
    st.error("❌ Impossible de récupérer la liste S&P 500 depuis toutes les sources.")
    return []

# ==============================
# Téléchargement data Yahoo
# ==============================
@st.cache_data
def download_data(ticker):
    df = yf.download(
        ticker,
        period="1y",
        interval="1d",
        progress=False,
        auto_adjust=False,
        group_by="column"
    )
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=["Close"])

# ==============================
# Calcul des MAs
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
# Logique principale
# ==============================
if st.sidebar.button("🚦 Lancer l'analyse"):
    tickers = get_sp500_tickers()

    if not tickers:
        st.error("Aucun ticker S&P 500 disponible. Vérifie la source (fichier local, Wikipedia, Slickcharts).")
        st.stop()

    # Optionnel : limite pour éviter de se faire rate-limit par Yahoo
    max_tickers = st.sidebar.number_input(
        "Nombre maximum de tickers à analyser",
        min_value=10,
        max_value=len(tickers),
        value=min(150, len(tickers)),
        step=10
    )
    tickers = tickers[:int(max_tickers)]

    detected = []
    with st.spinner(f"Analyse de {len(tickers)} tickers en {ma_type}..."):
        for ticker in tickers:
            df = download_data(ticker)
            if df is None or len(df) < 200:
                continue
            df = calculate_mas(df, ma_type)
            last = df.dropna().iloc[-1]
            ma50, ma200 = last["MA50"], last["MA200"]
            if ma200 == 0:
                continue
            ecart = abs(ma50 - ma200) / ma200 * 100
                        if ecart <= seuil:
                tendance = (
                    "Golden Cross imminent"
                    if ma50 < ma200
                    else "Death Cross imminent"
                )

                detected.append({
                    "Ticker": ticker,
                    "Prix": round(last["Close"], 2),
                    f"{ma_type}50": round(ma50, 2),
                    f"{ma_type}200": round(ma200, 2),
                    "Ecart(%)": round(ecart, 2),
                    "Signal": tendance
                })


    if detected:
        df_res = pd.DataFrame(detected).sort_values("Ecart(%)")
        st.success(f"{len(df_res)} signaux détectés avec un seuil de {seuil}% en {ma_type}.")
        st.dataframe(df_res, use_container_width=True)

        ticker_choice = st.selectbox("📌 Sélectionne un ticker à afficher :", df_res["Ticker"])
        if ticker_choice:
            df_sel = download_data(ticker_choice)
            df_sel = calculate_mas(df_sel, ma_type).dropna()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_sel.index, y=df_sel["Close"], name="Close"))
            fig.add_trace(go.Scatter(x=df_sel.index, y=df_sel["MA50"], name=f"{ma_type}50"))
            fig.add_trace(go.Scatter(x=df_sel.index, y=df_sel["MA200"], name=f"{ma_type}200"))
            fig.update_layout(
                title=f"Graphique : {ticker_choice} ({ma_type})",
                xaxis_title="Date",
                yaxis_title="Prix"
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"Aucun signal trouvé avec ce seuil en {ma_type}.")
else:
    st.info("Clique sur le bouton dans la barre latérale pour lancer l'analyse.")
