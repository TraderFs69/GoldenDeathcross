import streamlit as st
}


# =====================================================
# DISCORD — ENVOI WEBHOOK (UNE SEULE FOIS)
# =====================================================
def send_to_discord(rows):
if not DISCORD_WEBHOOK:
return
if rows is None or len(rows) == 0:
return


lines = []
for r in rows[:25]:
lines.append(
f"{r[1]} **{r[0]}** | SMA50 {r[2]} | SMA200 {r[3]} | Δ {r[4]}%"
)


message = (
"📊 **SMA 50 / SMA 200 — Proximité de cross (prix ajustés)**\n\n"
+ "\n".join(lines)
)


payload = {"content": message[:1900]}


try:
SESSION.post(DISCORD_WEBHOOK, json=payload, timeout=5)
except Exception:
pass


# =====================================================
# UI STREAMLIT
# =====================================================
st.title("📊 SMA 50 / SMA 200 — Distance ACTUELLE (aligné TradingView)")


limit = st.slider(
"Nombre de tickers à analyser",
min_value=50,
max_value=len(TICKERS),
value=300
)


threshold = st.slider(
"Distance max (%) pour alerte Discord",
0.1, 5.0, 1.0, 0.1
)


if st.button("🚀 Scanner et envoyer sur Discord"):
rows = []


with st.spinner("Scan en cours…"):
for t in TICKERS[:limit]:
df = get_data(t)
time.sleep(SLEEP_BETWEEN_CALLS)


if df is None:
continue


info = sma_proximity(df)
if info and abs(info["Distance (%)"]) <= threshold:
rows.append([
t,
info["Bias"],
info["SMA50"],
info["SMA200"],
info["Distance (%)"]
])


if rows:
result = (
pd.DataFrame(
rows,
columns=["Ticker", "Signal", "SMA50", "SMA200", "Distance (%)"]
)
.sort_values("Distance (%)", key=lambda x: abs(x))
)


st.dataframe(result, width="stretch")
send_to_discord(rows)


st.success(
f"{len(rows)} tickers proches d’un cross potentiel envoyés sur Discord ✅"
)
else:
st.info("Aucun ticker proche d’un cross avec les critères actuels.")
