import os
import time
import hmac
import hashlib
import threading
import requests
import pandas as pd
import pandas_ta as ta
from urllib.parse import urlencode
from flask import Flask
from datetime import datetime

# API ключи из переменных окружения
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
        signed_params = sign_request(params)
        url = f"{base_url}{path}?{urlencode(signed_params)}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("data", [])
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Exception fetching kline for {symbol}: {e}")
    return []


def calculate_indicators(klines):
    df = pd.DataFrame(klines)
    if df.empty or len(df) < 35:
        return None

    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    df.ta.macd(close="close", fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(close="close", length=14, append=True)
    df.ta.willr(length=14, append=True)

    macd = df["MACD_12_26_9"].iloc[-1]
    signal = df["MACDs_12_26_9"].iloc[-1]
    rsi = df["RSI_14"].iloc[-1]
    wr = df["WILLR_14"].iloc[-1]

    pattern = ""
    if wr > -20 and macd < signal and rsi > 50:
        pattern = "Возможен шорт"
    elif wr < -80 and macd > signal and 40 < rsi < 60:
        pattern = "Возможен лонг"
    elif -80 < wr < -20:
        pattern = "Рынок во флете или зоне перекупленности/перепроданности"

    return {
        "macd": macd,
        "signal": signal,
        "rsi": rsi,
        "wr": wr,
        "pattern": pattern
    }


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print(f"Ошибка отправки сообщения: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Ошибка Telegram: {e}")


btc_levels = {
    "resistance": [93400, 94000, 94700],
    "support": [92700, 91800, 90600],
    "danger": [89800],
    "breakout": [95500]
}


def check_btc_levels():
    symbol = "BTC-USDT"
    klines = get_kline(symbol)
    if not klines:
        return

    price = float(klines[-1]["close"])
    ind = calculate_indicators(klines)
    if not ind:
        return

    pattern = ind.get("pattern", "")
    text = f"\n<b>BTC/USDT: {price:.2f}</b>\n{pattern}\n"

    for level in btc_levels["resistance"]:
        if abs(price - level) <= 20:
            text += f"\n⚠️ <b>Сопротивление {level}</b> — возможна фиксация прибыли или шорт"

    for level in btc_levels["support"]:
        if abs(price - level) <= 20:
            text += f"\n🟢 <b>Поддержка {level}</b> — возможен вход в лонг"

    for level in btc_levels["breakout"]:
        if price >= level:
            text += f"\n🚀 <b>Пробой {level}!</b> Возможен импульс вверх"

    for level in btc_levels["danger"]:
        if price <= level:
            text += f"\n🔻 <b>Опасная зона {level}</b> — будь осторожен!"

    send_telegram_message(text)


def analyze():
    for symbol in symbols:
        klines = get_kline(symbol)
        if not klines:
            continue
        indicators = calculate_indicators(klines)
        if indicators:
            text = (
                f"<b>{symbol}</b>\n"
                f"Цена: {klines[-1]['close']}\n"
                f"MACD: {indicators['macd']:.2f}\n"
                f"Signal: {indicators['signal']:.2f}\n"
                f"RSI: {indicators['rsi']:.2f}\n"
                f"WR: {indicators['wr']:.2f}\n"
                f"<b>{indicators['pattern']}</b>"
            )
            send_telegram_message(text)


def run_bot():
    global bot_started
    if bot_started:
        return
    bot_started = True
    while True:
        try:
            analyze()
            check_btc_levels()
        except Exception as e:
            print(f"Ошибка в боте: {e}")
        time.sleep(300)  # 5 минут


@app.route('/')
def home():
    return "Bot is running!"


if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
