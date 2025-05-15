import os
import time
import hmac
import hashlib
import threading
import requests
import json
import pandas as pd
import pandas_ta as ta
from urllib.parse import urlencode
from flask import Flask

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

symbols = ["BTC-USDT", "TIA-USDT", "PEOPLE-USDT", "POPCAT-USDT", "DOGE-USDT"]
base_url = "https://open-api.bingx.com"
headers = {"X-BX-APIKEY": API_KEY}

app = Flask(__name__)
bot_started = False

def sign_request(params):
    query = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

def get_kline(symbol, interval="1m", limit=200):
    path = '/openApi/swap/v3/quote/klines'
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "timestamp": str(int(time.time() * 1000))
    }
    try:
        signed = sign_request(params.copy())
        url = f"{base_url}{path}?{urlencode(signed)}"
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        response_data = res.json()
        if 'data' in response_data and response_data['data']:
            return response_data['data']
    except Exception as e:
        send_telegram_message(f"Ошибка при получении свечей {symbol}: {e}")
    return []

def calculate_indicators(klines):
    df = pd.DataFrame(klines)
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)

    if len(df) < 50:
        return None

    try:
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9).dropna()
        rsi = ta.rsi(df["close"], length=14).dropna()
        ema = ta.ema(df["close"], length=21).dropna()
        wr = ta.willr(df["high"], df["low"], df["close"], length=14).dropna()
        atr = ta.atr(df["high"], df["low"], df["close"], length=14).dropna()

        fibo_618 = df["close"].iloc[-1] * 0.618
        fibo_5 = df["close"].iloc[-1] * 0.5
        fibo_382 = df["close"].iloc[-1] * 0.382

        return {
            "macd": macd["MACD_12_26_9"].iloc[-1],
            "macd_signal": macd["MACDs_12_26_9"].iloc[-1],
            "rsi": rsi.iloc[-1],
            "wr": wr.iloc[-1],
            "ema": ema.iloc[-1],
            "ema_prev": ema.iloc[-2] if len(ema) > 1 else ema.iloc[-1],
            "volume": df["volume"].iloc[-1],
            "volume_prev": df["volume"].iloc[-2] if len(df) > 1 else df["volume"].iloc[-1],
            "atr": atr.iloc[-1],
            "price": df["close"].iloc[-1],
            "fibo_618": fibo_618,
            "fibo_5": fibo_5,
            "fibo_382": fibo_382
        }
    except Exception as e:
        send_telegram_message(f"Ошибка в расчете индикаторов: {e}")
        return None

def is_touching_fibo(price, level, tol=0.005):
    # Проверка, находится ли цена в пределах 0.5% от уровня Фибоначчи
    return abs(price - level) / level <= tol

def get_signal(symbol):
    klines = get_kline(symbol)
    if not klines or len(klines) < 50:
        return f"⚠️ {symbol.replace('-USDT','')}: Недостаточно данных"

    indicators = calculate_indicators(klines)
    if not indicators:
        return f"⚠️ {symbol.replace('-USDT','')}: Ошибка индикаторов"

    price = indicators['price']
    fibo_levels = [indicators['fibo_382'], indicators['fibo_5'], indicators['fibo_618']]
    fibo_touch = any(is_touching_fibo(price, level) for level in fibo_levels)

    long_conditions = (
        indicators["macd"] > indicators["macd_signal"]
        and indicators["rsi"] < 50
        and indicators["wr"] < -80
        and indicators["volume"] > indicators["volume_prev"]
        and price > indicators["ema"]
        and fibo_touch
    )

    short_conditions = (
        indicators["macd"] < indicators["macd_signal"]
        and indicators["rsi"] > 60
        and indicators["wr"] > -20
        and indicators["volume"] > indicators["volume_prev"]
        and price < indicators["ema"]
        and fibo_touch
    )

    tp_long = price + 1.5 * indicators["atr"]
    sl_long = price - 1 * indicators["atr"]
    tp_short = price - 1.5 * indicators["atr"]
    sl_short = price + 1 * indicators["atr"]

    if long_conditions:
        return (f"🔵 ЛОНГ {symbol.replace('-USDT','')}\n"
                f"Вход: {price:.4f}\nTP: {tp_long:.4f}, SL: {sl_long:.4f}\n"
                f"Фибо уровень касания")

    elif short_conditions:
        return (f"🔴 ШОРТ {symbol.replace('-USDT','')}\n"
                f"Вход: {price:.4f}\nTP: {tp_short:.4f}, SL: {sl_short:.4f}\n"
                f"Фибо уровень касания")

    return f"⚪ {symbol.replace('-USDT','')}: Пока нет сигнала"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram: {e}")

def check_signals():
    for symbol in symbols:
        signal = get_signal(symbol)
        send_telegram_message(signal)

def send_status_update():
    status = "Бот работает, мой господин. Текущие цены:\n"
    for symbol in symbols:
        klines = get_kline(symbol)
        if klines:
            last_price = klines[-1]["close"]
            status += f"{symbol.replace('-USDT','')}: {last_price}\n"
    send_telegram_message(status)

def start_bot():
    global bot_started
    if not bot_started:
        bot_started = True
        check_signals()
        send_status_update()
        while True:
            time.sleep(30 * 60)  # каждые 30 минут
            check_signals()
            send_status_update()

@app.route("/")
def home():
    return "Bot is running!", 200

if __name__ == "__main__":
    threading.Thread(target=start_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
