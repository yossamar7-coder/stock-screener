"""
Claude x יוסי — Stock Screener & Alert
מסרוק מניות יומי עם התראה אוטומטית ל-Slack
"""

import os
import yfinance as yf
import json
import urllib.request
from datetime import datetime
import time
import sys

CONFIG = {
    "min_market_cap_b":  1,
    "max_market_cap_b":  50,
    "min_volume_ratio":  2.0,
    "rsi_min":           25,
    "rsi_max":           55,
    "min_price":         5,
    "max_results":       15,
}

CONFIG_MAG7 = {
    "min_volume_ratio":  1.2,
    "rsi_min":           30,
    "rsi_max":           70,
    "min_price":         5,
}

MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

WATCHLIST = [
    # Tech / AI / Semiconductors
    "AMD", "INTC", "QCOM", "AVGO", "TSM", "ARM", "SMCI", "MRVL",
    "PLTR", "SNOW", "DDOG", "MDB", "CRWD", "ZS", "OKTA", "PANW",
    "UBER", "LYFT", "ABNB", "DASH", "RBLX", "U", "TTWO",
    "ANET", "NET", "DKNG", "BILL", "GTLB", "PATH",
    "NBIS", "CIFR", "BWXT", "QXO", "HP", "KEEL", "CHRD",
    "SEDG", "CF", "PCAR",
    # Biotech / Healthcare
    "MRNA", "BNTX", "NVAX", "RXRX", "ILMN", "PACB", "TDOC",
    "EXAS", "BEAM", "EDIT", "CRSP", "FATE", "NTLA", "SNDX",
    "IMVT", "KROS", "GKOS", "PRCT", "CELH", "HIMS",
    "ACAD", "ITCI", "INSM", "RCKT", "KRYS", "VRTX",
    "ALNY", "IONS", "SRPT", "BMRN", "RARE", "FOLD",
    # Fintech / Crypto
    "AFRM", "UPST", "NU", "HOOD", "COIN", "RIOT", "MARA",
    "SOFI", "LC", "OPEN", "TREE", "CLOV", "UWMC",
    "MSTR", "CLSK", "IREN", "BTBT", "HUT", "CIFR",
    # EV / Clean Energy
    "RIVN", "LCID", "NIO", "LI", "XPEV", "CHPT", "BLNK", "PLUG",
    "FCEL", "BE", "STEM", "SPWR", "RUN", "ARRY",
    "CHPT", "EVGO", "BLNK", "LEV", "SOLO",
    # Consumer / Social / E-commerce
    "CVNA", "CPNG", "W", "ETSY", "PINS", "SNAP", "RDDT",
    "WISH", "REAL", "RENT", "BARK", "MAPS",
    "OPEN", "OPAD", "PTON", "NKLA", "GOEV",
    # Space / Defense / Industrial
    "RKLB", "ASTS", "LUNR", "JOBY", "ACHR", "SPCE",
    "KTOS", "AVAV", "LOAR", "POWL", "AMSC",
    # Energy / Commodities
    "CF", "PCAR", "CHRD", "KEEL", "HP",
    "SM", "CIVI", "MTDR", "ESTE", "REX",
    "CLF", "STLD", "CMC", "ZEUS", "WIRE",
    # Software / Cloud
    "APP", "TTGT", "RXST", "IONQ",
    "SMAR", "JAMF", "BRZE", "PCVX", "SEMR",
    "DV", "IS", "ALTR", "TASK", "FRSH",
    "MNDY", "ASAN", "BASE", "WEAV", "CFLT",
    # Semiconductors extra
    "WOLF", "AMBA", "AEHR", "CEVA", "ONTO",
    "ACMR", "COHU", "ICHR", "KLIC", "MCHP",
    # Growth misc
    "RELY", "STEP", "HLNE", "TFIN", "CARG",
    "SWTX", "RVNC", "TGTX", "ARDX", "APLS",
    "NARI", "INSP", "SWAV", "NVST", "OMCL",
    "AGIO", "PTGX", "VCEL", "HRMY", "CGEM",
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

def analyze_stock(symbol, config):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        market_cap = info.get("marketCap", 0) or 0
        market_cap_b = market_cap / 1e9
        if "max_market_cap_b" in config:
            if market_cap_b < config["min_market_cap_b"] or market_cap_b > config["max_market_cap_b"]:
                return None
        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        if not price or price < config["min_price"]:
            return None
        vol_today = info.get("volume", 0) or 0
        vol_avg = info.get("averageVolume", 0) or 0
        if vol_avg == 0:
            return None
        vol_ratio = vol_today / vol_avg
        if vol_ratio < config["min_volume_ratio"]:
            return None
        hist = ticker.history(period="30d")
        if hist.empty or len(hist) < 15:
            return None
        closes = hist["Close"].tolist()
        rsi = calculate_rsi(closes)
        if rsi is None or rsi < config["rsi_min"] or rsi > config["rsi_max"]:
            return None
        prev_close = info.get("previousClose", price)
        day_change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
        name = info.get("shortName") or info.get("longName") or symbol
        score = 0
        score += min(vol_ratio * 15, 40)
        score += max(0, (55 - rsi) * 0.8)
        score += min(abs(day_change_pct) * 3, 20)
        score += min(market_cap_b * 0.5, 10)
        score = min(round(score), 100)
        return {
            "symbol": symbol,
            "name": name,
            "price": round(price, 2),
            "day_change_pct": round(day_change_pct, 2),
            "volume_ratio": round(vol_ratio, 1),
            "rsi": rsi,
            "market_cap_b": round(market_cap_b, 1),
            "score": score,
        }
    except Exception:
        return None

def run_screener():
    print(f"\n⭐ סורק 7 המופלאים...")
    mag7_results = []
    for sym in MAG7:
        sys.stdout.write(f"\r   {sym}...")
        sys.stdout.flush()
        result = analyze_stock(sym, CONFIG_MAG7)
        if result:
            mag7_results.append(result)
        time.sleep(0.3)
    print(f"\n   נמצאו {len(mag7_results)} מופלאים עם סיגנל\n")

    print(f"\n🔍 מתחיל סריקה של {len(WATCHLIST)} מניות...")
    results = []
    for i, sym in enumerate(WATCHLIST):
        sys.stdout.write(f"\r   סורק {i+1}/{len(WATCHLIST)}: {sym:<8}")
        sys.stdout.flush()
        result = analyze_stock(sym, CONFIG)
        if result:
            results.append(result)
        time.sleep(0.3)
    print(f"\n\n✅ נמצאו {len(results)} מניות\n")
    results.sort(key=lambda x: x["score"], reverse=True)
    return mag7_results, results[:CONFIG["max_results"]]

def send_notification(mag7_results, stocks, scan_time):
    webhook_url = os.environ.get("SLACK_WEBHOOK")
    if not webhook_url:
        print("⚠️  מדפיס תוצאות:")
        if mag7_results:
            print("\n⭐ 7 המופלאים:")
            for s in mag7_results:
                print(f"   {s['symbol']:6} | ${s['price']:8.2f} | {s['day_change_pct']:+.1f}% | נפח {s['volume_ratio']}× | RSI {s['rsi']} | ציון {s['score']}/100")
        if stocks:
            print("\n🔍 מניות נוספות:")
            for s in stocks:
                print(f"   {s['symbol']:6} | ${s['price']:8.2f} | {s['day_change_pct']:+.1f}% | נפח {s['volume_ratio']}× | RSI {s['rsi']} | ציון {s['score']}/100")
        return

    def post(text):
        data = json.dumps({"text": text}).encode()
        req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            time.sleep(0.5)
        except Exception as e:
            print(f"שגיאה: {e}")

    post(
        f":bar_chart: *Claude x יוסי Screener* | {scan_time}\n"
        f":star: מופלאים: *{len(mag7_results)}* | :mag: מניות: *{len(stocks)}*\n"
        f":warning: מועמדים טכניים בלבד — לא המלצת קנייה!"
    )

    if mag7_results:
        post("━━━━━━━━━━\n:star: *7 המופלאים — סיגנל היום:*")
        for s in mag7_results:
            arrow = ":large_green_circle:" if s['day_change_pct'] >= 0 else ":red_circle:"
            post(
                f"{arrow} *{s['symbol']}* — {s['name']}\n"
                f":moneybag: *${s['price']}* ({s['day_change_pct']:+.2f}%) | נפח: *{s['volume_ratio']}x* | RSI: *{s['rsi']}*\n"
                f":star: ציון: *{s['score']}/100*"
            )

    if stocks:
        post("━━━━━━━━━━\n:mag: *מניות נוספות:*")
        for s in stocks:
            arrow = ":large_green_circle:" if s['day_change_pct'] >= 0 else ":red_circle:"
            post(
                f"{arrow} *{s['symbol']}* — {s['name']}\n"
                f":moneybag: *${s['price']}* ({s['day_change_pct']:+.2f}%) | נפח: *{s['volume_ratio']}x* | RSI: *{s['rsi']}*\n"
                f":star: ציון: *{s['score']}/100*"
            )

    print(f"✅ נשלח ל-Slack!")

if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║   Claude × יוסי — Stock Screener        ║")
    print("╚══════════════════════════════════════════╝")
    scan_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    mag7_results, stocks = run_screener()
    if mag7_results or stocks:
        print("🏆 תוצאות מובילות:")
        for s in (mag7_results + stocks)[:5]:
            print(f"   {s['symbol']:6} | ${s['price']:8.2f} | נפח {s['volume_ratio']}× | RSI {s['rsi']:5.1f} | ציון {s['score']}/100")
    send_notification(mag7_results, stocks, scan_time)
    print("\n✅ סיום.")
