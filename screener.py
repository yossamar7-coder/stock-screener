"""
Claude x יוסי — Stock Screener Ultimate v3
עם Slack במקום Discord
"""

import os
import yfinance as yf
import json
import urllib.request
from datetime import datetime
import time
import sys
import requests
from requests import Session

def get_session():
    s = Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    return s

CONFIG = {
    "min_market_cap_b":  1,
    "max_market_cap_b":  500,
    "min_volume_ratio":  1.5,
    "rsi_min":           20,
    "rsi_max":           65,
    "min_price":         3,
    "max_results":       15,
}

CONFIG_MAG7 = {
    "min_volume_ratio":  1.2,
    "rsi_min":           30,
    "rsi_max":           70,
}

MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

WATCHLIST = [
    "AMD", "INTC", "QCOM", "AVGO", "TSM", "ARM", "SMCI", "MRVL",
    "PLTR", "SNOW", "DDOG", "MDB", "CRWD", "ZS", "OKTA", "PANW",
    "UBER", "LYFT", "ABNB", "DASH", "RBLX", "U", "TTWO",
    "ANET", "NET", "DKNG", "BILL", "GTLB", "PATH",
    "MRNA", "BNTX", "NVAX", "RXRX", "ILMN", "PACB", "TDOC",
    "EXAS", "BEAM", "EDIT", "CRSP",
    "AFRM", "UPST", "NU", "HOOD", "COIN", "RIOT", "MARA",
    "SOFI", "LC",
    "RIVN", "LCID", "NIO", "LI", "XPEV", "CHPT", "PLUG",
    "FCEL", "BE",
    "CVNA", "CPNG", "W", "ETSY", "PINS", "SNAP", "RDDT",
    "RKLB", "ASTS", "LUNR", "JOBY", "ACHR",
    "APP", "HIMS", "NKLA", "MSTR", "IONQ",
    "CELH", "IMVT", "KROS", "GKOS", "PRCT",
]

WATCHLIST = list(dict.fromkeys(WATCHLIST))

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

def get_ma150_signal(hist_closes, current_price):
    try:
        if len(hist_closes) < 150:
            return 0, "אין מספיק היסטוריה"
        ma150 = sum(hist_closes[-150:]) / 150
        if len(hist_closes) >= 160:
            ma150_old = sum(hist_closes[-160:-10]) / 150
            ma_trend_up = ma150 > ma150_old
        else:
            ma_trend_up = None
        pct_vs_ma = ((current_price - ma150) / ma150) * 100
        if pct_vs_ma < 0:
            if ma_trend_up is True:
                return 20, f"מתחת MA150 ({pct_vs_ma:.1f}%) + מגמה עולה :white_check_mark:"
            elif ma_trend_up is False:
                return -30, f"מתחת MA150 ({pct_vs_ma:.1f}%) + מגמה יורדת :warning:"
            else:
                return 5, f"מתחת MA150 ({pct_vs_ma:.1f}%)"
        elif pct_vs_ma <= 12:
            return 15, f"מעל MA150 {pct_vs_ma:.1f}% :white_check_mark:"
        else:
            return 0, f"מעל MA150 {pct_vs_ma:.1f}% — ממתין לתיקון"
    except Exception:
        return 0, "לא ניתן לחשב MA150"

def get_analyst_signal(info):
    recommendation = info.get("recommendationKey", "").lower()
    score = 0
    if recommendation in ["strong_buy", "strongbuy"]:
        score = 15
    elif recommendation == "buy":
        score = 10
    elif recommendation == "hold":
        score = -5
    elif recommendation in ["underperform", "sell", "strong_sell"]:
        score = -25
    return score, recommendation or "אין"

def get_operating_income_signal(info):
    try:
        op_income = info.get("operatingIncome", None)
        total_revenue = info.get("totalRevenue", None)
        if op_income is None or total_revenue is None or total_revenue == 0:
            return 0, "אין נתונים"
        ratio = op_income / total_revenue
        if ratio >= 0:
            return 5, f"רווח תפעולי {ratio*100:.1f}%"
        elif ratio >= -0.2:
            return -5, f"הפסד קל {ratio*100:.1f}%"
        elif ratio >= -0.5:
            return -15, f"הפסד {ratio*100:.1f}%"
        else:
            return -25, f"הפסד גבוה {ratio*100:.1f}%"
    except Exception:
        return 0, "אין נתונים"

def analyze_stock(symbol, session, config):
    try:
        ticker = yf.Ticker(symbol, session=session)
        info = ticker.info

        market_cap = info.get("marketCap", 0) or 0
        market_cap_b = market_cap / 1e9

        if "max_market_cap_b" in config:
            if market_cap_b < config["min_market_cap_b"] or market_cap_b > config["max_market_cap_b"]:
                return None

        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        if not price or price < config.get("min_price", 0):
            return None

        vol_today = info.get("volume", 0) or 0
        vol_avg = info.get("averageVolume", 0) or 0
        if vol_avg == 0:
            return None
        vol_ratio = vol_today / vol_avg
        if vol_ratio < 1.0:  # רק סינון בסיסי מאוד
            return None

        hist = ticker.history(period="200d")
        if hist.empty or len(hist) < 15:
            return None
        closes = hist["Close"].tolist()

        rsi = calculate_rsi(closes[-30:])
        if rsi is None:
            return None
        # RSI affects score only, not a hard filter

        prev_close = info.get("previousClose", price)
        day_change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
        name = info.get("shortName") or info.get("longName") or symbol

        score = 0
        score += min(vol_ratio * 15, 40)
        score += max(0, (55 - rsi) * 0.8)
        score += min(abs(day_change_pct) * 3, 20)
        score += min(market_cap_b * 0.3, 8)

        ma150_score, ma150_desc = get_ma150_signal(closes, price)
        score += ma150_score

        analyst_score, analyst_rec = get_analyst_signal(info)
        score += analyst_score

        op_score, op_desc = get_operating_income_signal(info)
        score += op_score

        score = min(max(round(score), 0), 100)

        return {
            "symbol": symbol,
            "name": name,
            "price": round(price, 2),
            "day_change_pct": round(day_change_pct, 2),
            "volume_ratio": round(vol_ratio, 1),
            "rsi": rsi,
            "market_cap_b": round(market_cap_b, 1),
            "score": score,
            "ma150_desc": ma150_desc,
            "analyst_rec": analyst_rec,
            "op_desc": op_desc,
        }
    except Exception:
        return None

def run_screener():
    session = get_session()

    print(f"\n:star: סורק 7 המופלאים...")
    mag7_results = []
    for sym in MAG7:
        sys.stdout.write(f"\r   {sym}...")
        sys.stdout.flush()
        result = analyze_stock(sym, session, CONFIG_MAG7)
        if result:
            mag7_results.append(result)
        time.sleep(0.5)
    print(f"\n   נמצאו {len(mag7_results)} מופלאים עם סיגנל\n")

    print(f":mag: סורק {len(WATCHLIST)} מניות נוספות...")
    results = []
    for i, sym in enumerate(WATCHLIST):
        sys.stdout.write(f"\r   סורק {i+1}/{len(WATCHLIST)}: {sym:<8}")
        sys.stdout.flush()
        result = analyze_stock(sym, session, CONFIG)
        if result:
            results.append(result)
        time.sleep(0.5)

    results.sort(key=lambda x: x["score"], reverse=True)
    print(f"\n\n:white_check_mark: נמצאו {len(results)} מניות רגילות\n")
    return mag7_results, results[:CONFIG["max_results"]]

def send_slack(mag7_results, stocks, scan_time):
    webhook_url = os.environ.get("SLACK_WEBHOOK")
    print(f"DEBUG: webhook_url = {webhook_url}")
    if not webhook_url:
        print("אין Webhook URL")
        for s in mag7_results + stocks:
            print(f"   {s['symbol']:6} | ${s['price']:8.2f} | ציון {s['score']}/100")
        return

    def post(text):
        data = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            webhook_url, data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req)
            time.sleep(0.3)
        except Exception as e:
            print(f"שגיאה: {e}")

    post(
        f":bar_chart: *Claude x יוסי Screener* | {scan_time}\n"
        f":star: מופלאים עם סיגנל: *{len(mag7_results)}* | :mag: מניות אחרות: *{len(stocks)}*\n"
        f":warning: מועמדים טכניים בלבד — לא המלצת קנייה!"
    )

    if mag7_results:
        post("━━━━━━━━━━\n:star: *7 המופלאים — סיגנל היום:*")
        for s in mag7_results:
            arrow = ":large_green_circle:" if s['day_change_pct'] >= 0 else ":red_circle:"
            post(
                f"{arrow} *{s['symbol']}* — {s['name']}\n"
                f":moneybag: *${s['price']}* ({s['day_change_pct']:+.2f}%) | נפח: *{s['volume_ratio']}x* | RSI: *{s['rsi']}*\n"
                f":chart_with_upwards_trend: {s['ma150_desc']}\n"
                f":man-office-worker: אנליסטים: {s['analyst_rec']} | {s['op_desc']}\n"
                f":star: ציון: *{s['score']}/100*"
            )

    if stocks:
        post("━━━━━━━━━━\n:mag: *מניות נוספות:*")
        for s in stocks:
            arrow = ":large_green_circle:" if s['day_change_pct'] >= 0 else ":red_circle:"
            post(
                f"{arrow} *{s['symbol']}* — {s['name']}\n"
                f":moneybag: *${s['price']}* ({s['day_change_pct']:+.2f}%) | נפח: *{s['volume_ratio']}x* | RSI: *{s['rsi']}*\n"
                f":chart_with_upwards_trend: {s['ma150_desc']}\n"
                f":man-office-worker: אנליסטים: {s['analyst_rec']} | {s['op_desc']}\n"
                f":star: ציון: *{s['score']}/100*"
            )

    print(f"נשלח ל-Slack!")

if __name__ == "__main__":
    print("Claude x יוסי — Stock Screener v3 Slack")
    scan_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    mag7_results, stocks = run_screener()
    send_slack(mag7_results, stocks, scan_time)
    print("\nסיום.")
