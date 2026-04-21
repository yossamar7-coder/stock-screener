"""
Claude x יוסי — Stock Screener & Alert
מסרוק מניות יומי עם התראה אוטומטית ל-Discord
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

WATCHLIST = [
    "AMD", "INTC", "QCOM", "AVGO", "TSM", "ARM", "SMCI", "MRVL",
    "PLTR", "SNOW", "DDOG", "MDB", "CRWD", "ZS", "OKTA", "PANW",
    "UBER", "LYFT", "ABNB", "DASH", "RBLX", "U", "TTWO",
    "MRNA", "BNTX", "NVAX", "RXRX", "ILMN", "PACB", "TDOC",
    "AFRM", "UPST", "NU", "HOOD", "COIN", "RIOT", "MARA",
    "RIVN", "LCID", "NIO", "LI", "XPEV", "CHPT", "BLNK", "PLUG",
    "CVNA", "CPNG", "W", "ETSY", "PINS", "SNAP", "RDDT",
    "RKLB", "ASTS", "LUNR", "JOBY", "ACHR",
    "APP", "TTGT", "HIMS", "RXST", "NKLA", "MSTR", "IONQ",
]

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

def analyze_stock(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        market_cap = info.get("marketCap", 0) or 0
        market_cap_b = market_cap / 1e9
        if market_cap_b < CONFIG["min_market_cap_b"] or market_cap_b > CONFIG["max_market_cap_b"]:
            return None
        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        if not price or price < CONFIG["min_price"]:
            return None
        vol_today = info.get("volume", 0) or 0
        vol_avg = info.get("averageVolume", 0) or 0
        if vol_avg == 0:
            return None
        vol_ratio = vol_today / vol_avg
        if vol_ratio < CONFIG["min_volume_ratio"]:
            return None
        hist = ticker.history(period="30d")
        if hist.empty or len(hist) < 15:
            return None
        closes = hist["Close"].tolist()
        rsi = calculate_rsi(closes)
        if rsi is None or rsi < CONFIG["rsi_min"] or rsi > CONFIG["rsi_max"]:
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
    print(f"\n🔍 מתחיל סריקה של {len(WATCHLIST)} מניות...")
    results = []
    for i, sym in enumerate(WATCHLIST):
        sys.stdout.write(f"\r   סורק {i+1}/{len(WATCHLIST)}: {sym:<8}")
        sys.stdout.flush()
        result = analyze_stock(sym)
        if result:
            results.append(result)
        time.sleep(0.3)
    print(f"\n\n✅ נמצאו {len(results)} מניות\n")
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:CONFIG["max_results"]]

def send_discord(stocks, scan_time):
    webhook_url = os.environ.get("DISCORD_WEBHOOK")
    if not webhook_url:
        print("⚠️  אין DISCORD_WEBHOOK — מדפיס תוצאות:")
        for s in stocks:
            print(f"   {s['symbol']:6} | ${s['price']:8.2f} | {s['day_change_pct']:+.1f}% | נפח {s['volume_ratio']}× | RSI {s['rsi']} | ציון {s['score']}/100")
        return

    # שלח הודעת כותרת
    header = f"📊 **Claude × יוסי Screener** | {scan_time}\n🔍 נמצאו **{len(stocks)} מניות**:\n⚠️ רשימת מועמדים טכניים בלבד — לא המלצת קנייה!"
    data = json.dumps({"content": header}).encode()
    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)
    time.sleep(0.5)

    if not stocks:
        return

    # שלח כל מניה
    for s in stocks:
        arrow = "🟢" if s['day_change_pct'] >= 0 else "🔴"
        msg = (
            f"{arrow} **{s['symbol']}** — {s['name']}\n"
            f"💰 מחיר: **${s['price']}** ({s['day_change_pct']:+.2f}%)\n"
            f"📈 נפח: **{s['volume_ratio']}×** מהממוצע\n"
            f"📊 RSI: **{s['rsi']}**\n"
            f"⭐ ציון: **{s['score']}/100**\n"
        )
        data = json.dumps({"content": msg}).encode()
        req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            time.sleep(0.5)
        except Exception as e:
            print(f"שגיאה בשליחת {s['symbol']}: {e}")

    print(f"✅ נשלח ל-Discord — {len(stocks)} מניות")

if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║   Claude × יוסי — Stock Screener        ║")
    print("╚══════════════════════════════════════════╝")
    scan_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    stocks = run_screener()
    if stocks:
        print("🏆 תוצאות מובילות:")
        for s in stocks[:5]:
            print(f"   {s['symbol']:6} | ${s['price']:8.2f} | נפח {s['volume_ratio']}× | RSI {s['rsi']:5.1f} | ציון {s['score']}/100")
    send_discord(stocks, scan_time)
    print("\n✅ סיום.")
