import os
import time
import pandas as pd
import requests

from io import StringIO
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =====================================================
# CONFIG
# =====================================================

POLYGON_KEY = os.getenv("POLYGON_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

SLEEP = 0.25
BATCH_SIZE = 15
HEARTBEAT_EVERY = 25

LIMIT = 200
THRESHOLD = 1.0

# =====================================================
# SESSION HTTP
# =====================================================

def build_session():
    session = requests.Session()

    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )

    adapter = HTTPAdapter(max_retries=retry)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

SESSION = build_session()

# =====================================================
# DISCORD
# =====================================================

def send_message(message):

    if not DISCORD_WEBHOOK:
        print("Webhook Discord manquant")
        return

    payload = {
        "content": message[:1900]
    }

    try:
        r = SESSION.post(
            DISCORD_WEBHOOK,
            json=payload,
            timeout=15
        )

        print("Discord:", r.status_code)

    except Exception as e:
        print("Discord Error:", e)


def send_csv(df):

    if df.empty:
        return

    csv_buffer = StringIO()

    df.to_csv(
        csv_buffer,
        index=False
    )

    csv_buffer.seek(0)

    files = {
        "file": (
            "scanner_results.csv",
            csv_buffer.getvalue(),
            "text/csv"
        )
    }

    try:
        r = SESSION.post(
            DISCORD_WEBHOOK,
            files=files,
            timeout=20
        )

        print("CSV envoyé:", r.status_code)

    except Exception as e:
        print("CSV Error:", e)

# =====================================================
# DATA
# =====================================================

def load_tickers():

    df = pd.read_excel(
        "russell3000_constituents.xlsx"
    )

    return (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .str.upper()
        .tolist()
    )


def get_sma(ticker, window):

    url = (
        f"https://api.polygon.io/v1/indicators/sma/{ticker}"
        f"?timespan=day"
        f"&window={window}"
        f"&series_type=close"
        f"&adjusted=true"
        f"&order=desc"
        f"&limit=2"
        f"&apiKey={POLYGON_KEY}"
    )

    try:

        r = SESSION.get(
            url,
            timeout=15
        )

        data = r.json()

        values = (
            data.get("results", {})
            .get("values", [])
        )

        if len(values) < 2:
            return None, None

        return (
            values[0]["value"],
            values[1]["value"]
        )

    except Exception:
        return None, None


def get_price(ticker):

    try:

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/"
            f"{ticker}/prev?apiKey={POLYGON_KEY}"
        )

        r = SESSION.get(
            url,
            timeout=15
        )

        data = r.json()

        return data["results"][0]["c"]

    except Exception:
        return None

# =====================================================
# SCORE
# =====================================================

def compute_score(dist, slope, golden):

    score = 0

    score += max(
        0,
        40 - abs(dist) * 10
    )

    score += min(
        30,
        abs(slope) * 200
    )

    if golden:
        score += 20

    return round(
        min(100, score),
        1
    )

# =====================================================
# MAIN
# =====================================================

def main():

    if not POLYGON_KEY:
        raise Exception(
            "POLYGON_API_KEY manquant"
        )

    tickers = load_tickers()

    send_message(
        f"🚀 Scan démarré ({LIMIT} tickers)"
    )

    results = []

    analysed = 0
    detected = 0

    for ticker in tickers[:LIMIT]:

        analysed += 1

        sma50, _ = get_sma(
            ticker,
            50
        )

        time.sleep(SLEEP)

        sma200, sma200_prev = get_sma(
            ticker,
            200
        )

        time.sleep(SLEEP)

        price = get_price(
            ticker
        )

        time.sleep(SLEEP)

        if None in (
            sma50,
            sma200,
            sma200_prev,
            price
        ):
            continue

        dist = (
            (sma50 - sma200)
            / sma200
            * 100
        )

        if abs(dist) > THRESHOLD:
            continue

        slope = sma200 - sma200_prev

        golden = sma50 < sma200

        score = compute_score(
            dist,
            slope,
            golden
        )

        signal = (
            "Golden"
            if golden
            else "Death"
        )

        detected += 1

        results.append([
            ticker,
            signal,
            round(price, 2),
            round(sma50, 2),
            round(sma200, 2),
            round(dist, 2),
            round(slope, 4),
            score
        ])

        if len(results) >= BATCH_SIZE:

            df = pd.DataFrame(
                results,
                columns=[
                    "Ticker",
                    "Signal",
                    "Price",
                    "SMA50",
                    "SMA200",
                    "Distance %",
                    "Slope",
                    "Score"
                ]
            )

            send_csv(df)

            results.clear()

        if analysed % HEARTBEAT_EVERY == 0:

            send_message(
                f"⏳ {analysed}/{LIMIT} analysés | "
                f"{detected} setups"
            )

    if results:

        df = pd.DataFrame(
            results,
            columns=[
                "Ticker",
                "Signal",
                "Price",
                "SMA50",
                "SMA200",
                "Distance %",
                "Slope",
                "Score"
            ]
        )

        send_csv(df)

    send_message(
        f"✅ Scan terminé\n"
        f"Analysés: {analysed}\n"
        f"Setups: {detected}"
    )

    print(
        f"Terminé | {analysed} analysés | "
        f"{detected} setups"
    )


if __name__ == "__main__":
    main()
