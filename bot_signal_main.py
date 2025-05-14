import os
import time
import hmac
import hashlib
import threading
import requests
import json
import pandas as pd
import pandas_ta as ta  # Используем pandas_ta
import numpy as np
from urllib.parse import urlencode
from flask import Flask

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = "8031738383:AAE3zxHvhSFhbTESh0dxEPaoODCrPnuOIxw"
TELEGRAM_CHAT_ID = "557172438"

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
    path = '/openApi/swap/v3/quote/klines'  # Новый путь для получения данных
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
        else:
            print(f"[Ответ от API] Нет данных для {symbol}")
            return []
    except Exception as e:
        print(f"[Ошибка get_kline] {symbol}: {e}")
        return []

def calculate_indicators(klines):
    df = pd.DataFrame(klines)
    df["close"] = df["close"].astype(float)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)

    # MACD
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)

    # RSI
    rsi = ta.rsi(df["close"], length=14)

    # EMA
    ema = ta.ema(df["close"], length=21)

    # Bollinger Bands
    bbands = ta.bbands(df["close"], length=20, std=2)

    # Stochastic Oscillator
    stoch = ta.stoch(df["high"], df["low"], df["close"], fastk_period=14, slowk_period=3, slowd_period=3)

    return {
        "macd": macd["MACD"].iloc[-1],
        "macd_signal": macd["MACDs"].iloc[-1],
        "rsi": rsi.iloc[-1],
        "ema": ema.iloc[-1],
        "upperband": bbands["BBU_20_2.0"].iloc[-1],
        "lowerband": bbands["BBL_20_2.0"].iloc[-1],
        "slowk": stoch["STOCHk_14_3_3"].iloc[-1],
        "slowd": stoch["STOCHd_14_3_3"].iloc[-1],
        "volume": df["volume"].iloc[-1],
        "ema_previous": ema.iloc[-2],  # предыдущий EMA для сравнения
        "volume_previous": df["volume"].iloc[-2]  # предыдущий объем
    }

def get_signal(symbol):
    klines = get_kline(symbol, "1m")
    if len(klines) >= 200:
        indicators = calculate_indicators(klines)

        # Условия для анализа тренда на основе MACD, RSI, EMA и объемов
        if indicators["macd"] > indicators["macd_signal"] and indicators["rsi"] < 30 and indicators["volume"] > indicators["volume_previous"]:
            if indicators["ema"] < indicators["ema_previous"]:
                return f"🔵 {symbol.replace('-USDT','')}: Лонг\nTP: {round(indicators['ema'] * 1.03, 5)}, SL: {round(indicators['ema'] * 0.97, 5)}"
        elif indicators["macd"] < indicators["macd_signal"] and indicators["rsi"] > 70 and indicators["volume"] > indicators["volume_previous"]:
            if indicators["ema"] > indicators["ema_previous"]:
                return f"🔴 {symbol.replace('-USDT','')}: Шорт\nTP: {round(indicators['ema'] * 0.97, 5)}, SL: {round(indicators['ema'] * 1.03, 5)}"
        else:
            return f"⚪ {symbol.replace('-USDT','')}: Нет сигнала"

    return f"⚠️ {symbol.replace('-USDT','')}: Недостаточно данных"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        res = requests.post(url, data=payload)
        if not res.ok:
            print("Ошибка отправки:", res.text)
    except Exception as e:
        print("Ошибка при отправке:", e)

def start_bot():
    while True:
        any_signals = False
        for symbol in symbols:
            try:
                signal = get_signal(symbol)
                if "данных нет" not in signal:
                    send_telegram_message(signal)  # Если есть данные — отправляем в Telegram
                    any_signals = True
            except Exception as e:
                print(f"[Ошибка при анализе {symbol}] {e}")
        if not any_signals:
            msg = "Бот работает, мой господин. Пока точек входа не найдено. я постараюсь работать лучше.\nТекущие цены:\n" + "\n".join([get_signal(sym) for sym in symbols])
            send_telegram_message(msg)
        time.sleep(300)

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
