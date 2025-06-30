
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="S&P 500 Golden/Death Cross Scanner", layout="wide")
st.title("📈 Scanner S&P 500 : Golden & Death Cross (SMA/EMA)")

st.sidebar.header("Configuration")
seuil = st.sidebar.slider("Seuil d'écart (%) pour signaler un croisement imminent", 0.1, 5.0, 1.0, step=0.1)
ma_type = st.sidebar.selectbox("Type de moyenne mobile :", ["SMA", "EMA"])

@st.cache_data
def get_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = pd.read_html(url)
    sp500_df = tables[0]
    return sp500_df["Symbol"].tolist()

@st.cache_data
def download_data(ticker):
    df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=False, group_by="column")
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=["Close"])

def calculate_mas(df, ma_type):
    if ma_type == "SMA":
        df["MA50"] = df["Close"].rolling(50).mean()
        df["MA200"] = df["Close"].rolling(200).mean()
    else:
        df["MA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["MA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df

if st.sidebar.button("🚦 Lancer l'analyse"):
    tickers = get_sp500_tickers()
    detected = []
    with st.spinner(f"Analyse des tickers en {ma_type}..."):
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
                tendance = "Golden Cross imminent" if ma50 < ma200 else "Death Cross imminent"
                detected.append({
                    "Ticker": ticker,
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
            fig.update_layout(title=f"Graphique : {ticker_choice} ({ma_type})", xaxis_title="Date", yaxis_title="Prix")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"Aucun signal trouvé avec ce seuil en {ma_type}.")
else:
    st.info("Clique sur le bouton pour lancer l'analyse.")
