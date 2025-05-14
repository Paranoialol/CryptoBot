import os
import time
import hmac
import hashlib
import threading
import requests
import json
import pandas as pd
from flask import Flask
from ta.momentum import RSIIndicator, WilliamsRIndicator
from ta.trend import MACD, EMAIndicator

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = "8031738383:AAE3zxHvhSFhbTESh0dxEPaoODCrPnuOIxw"
TELEGRAM_CHAT_ID = "557172438"

symbols = ["BTC-USDT", "TIA-USDT", "PEOPLE-USDT", "POPCAT-USDT", "DOGE-USDT"]
base_url = "https://open-api.bingx.com/openApi/swap/quote/v1/kline"
headers = {"X-BX-APIKEY": API_KEY}

app = Flask(__name__)
bot_started = False

def sign_request(params):
    query = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

def get_kline(symbol, interval="1m"):
    params = {"symbol": symbol, "interval": interval, "limit": 2}
    try:
        signed = sign_request(params.copy())
        res = requests.get(base_url, headers=headers, params=signed)
        res.raise_for_status()
        return res.json().get("data", [])
    except Exception as e:
        print(f"[Ошибка get_kline] {symbol}: {e}")
        return []

def get_price_change(symbol):
    klines = get_kline(symbol, "1m")
    if len(klines) >= 2:
        last = float(klines[-1][4])
        prev = float(klines[-2][4])
        diff = last - prev
        if diff > 0:
            color = "🟢"
        elif diff < 0:
            color = "🔴"
        else:
            color = "⚪"
        return f"{color} {symbol.replace('-USDT','')}: {last:.2f}"
    return f"⚠️ {symbol.replace('-USDT','')}: данных нет"

def get_indicators(df):
    df["close"] = df["close"].astype(float)
    macd = MACD(close=df["close"]).macd_diff().iloc[-1]
    rsi = RSIIndicator(close=df["close"]).rsi().iloc[-1]
    wr = WilliamsRIndicator(high=df["high"], low=df["low"], close=df["close"]).williams_r().iloc[-1]
    ema = EMAIndicator(close=df["close"], window=20).ema_indicator().iloc[-1]
    return macd, rsi, wr, ema

def get_levels(df):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    resistance = max(high[-20:])
    support = min(low[-20:])
    return resistance, support

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        res = requests.post(url, data=payload)
        if not res.ok:
            print("Ошибка отправки:", res.text)
    except Exception as e:
        print("Ошибка при отправке:", e)

def analyze_symbol(symbol):
    found = False
    for interval in ["1m", "5m", "15m", "1h"]:
        raw = get_kline(symbol, interval)
        if not raw:
            continue
        df = pd.DataFrame(raw)
        df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
        df = df.astype(float)

        macd, rsi, wr, ema = get_indicators(df)
        resistance, support = get_levels(df)
        last_price = float(df["close"].iloc[-1])

        if macd > 0 and rsi > 45 and wr > -80 and last_price > ema:
            signal = "ЛОНГ"
        elif macd < 0 and rsi < 55 and wr < -20 and last_price < ema:
            signal = "ШОРТ"
        else:
            continue

        msg = (
            f"Монета: {symbol.replace('-USDT','')}\n"
            f"Таймфрейм: {interval}\n"
            f"Сигнал: {signal}\n"
            f"Цена: {last_price:.2f}\n"
            f"TP: {resistance:.2f} | SL: {support:.2f}\n"
            f"MACD: {macd:.4f}, RSI: {rsi:.2f}, WR: {wr:.2f}, EMA: {ema:.2f}"
        )
        send_telegram_message(msg)
        found = True
        break
    return found

def start_bot():
    while True:
        any_signals = False
        for symbol in symbols:
            try:
                if analyze_symbol(symbol):
                    any_signals = True
            except Exception as e:
                print(f"[Анализ ошибки] {symbol}: {e}")
        if not any_signals:
            prices = [get_price_change(sym) for sym in symbols]
            msg = "Бот работает. Пока точек входа не найдено.\nТекущие цены:\n" + "\n".join(prices)
            send_telegram_message(msg)
        time.sleep(1800)

@app.route('/')
def home():
    global bot_started
    if not bot_started:
        thread = threading.Thread(target=start_bot)
        thread.daemon = True
        thread.start()
        bot_started = True
    return "Бот запущен и работает в фоне."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
