import os
import time
import hmac
import hashlib
import requests
import json
import pandas as pd
import pandas_ta as ta
from urllib.parse import urlencode
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

symbols = ["BTC-USDT", "TIA-USDT", "PEOPLE-USDT", "POPCAT-USDT", "DOGE-USDT"]
base_url = "https://open-api.bingx.com"
headers = {"X-BX-APIKEY": API_KEY}

app = Flask(__name__)

def sign_request(params):
    query = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

def get_kline(symbol, interval="1m", limit=100):
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
        else:
            return []
    except Exception as e:
        send_telegram_message(f"❗Ошибка получения данных {symbol}: {e}")
        return []

def calculate_indicators(klines):
    df = pd.DataFrame(klines)
    if df.empty:
        return None
    for col in ["close", "open", "high", "low", "volume"]:
        df[col] = df[col].astype(float)
    df.dropna(inplace=True)
    if len(df) < 50:
        return None
    try:
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9).dropna()
        rsi = ta.rsi(df["close"], length=14).dropna()
        ema = ta.ema(df["close"], length=21).dropna()
        wr = ta.wr(df["high"], df["low"], df["close"], length=14).dropna()
        volume = df["volume"]
        close = df["close"]

        # Последние значения индикаторов
        return {
            "macd": macd["MACD_12_26_9"].iloc[-1],
            "macd_signal": macd["MACDs_12_26_9"].iloc[-1],
            "rsi": rsi.iloc[-1],
            "ema": ema.iloc[-1],
            "ema_previous": ema.iloc[-2] if len(ema) > 1 else ema.iloc[-1],
            "wr": wr.iloc[-1],
            "wr_previous": wr.iloc[-2] if len(wr) > 1 else wr.iloc[-1],
            "volume": volume.iloc[-1],
            "volume_previous": volume.iloc[-2] if len(volume) > 1 else volume.iloc[-1],
            "close": close.iloc[-1],
            "close_previous": close.iloc[-2] if len(close) > 1 else close.iloc[-1],
            "close_series": close
        }
    except Exception as e:
        send_telegram_message(f"❗Ошибка расчёта индикаторов: {e}")
        return None

def calculate_fibonacci_levels(close_series):
    max_price = close_series.max()
    min_price = close_series.min()
    diff = max_price - min_price
    levels = {
        "0.382": round(max_price - 0.382 * diff, 5),
        "0.5": round(max_price - 0.5 * diff, 5),
        "0.618": round(max_price - 0.618 * diff, 5),
    }
    return levels

def volume_trending_up(volume, volume_previous):
    return volume > volume_previous

def price_touching_level(price, level, threshold=0.002):
    # цена касается уровня если разница менее 0.2%
    return abs(price - level) / level <= threshold

def get_signal(symbol):
    klines = get_kline(symbol)
    if len(klines) < 50:
        return f"⚪ {symbol.replace('-USDT','')}: Недостаточно данных для анализа"
    indicators = calculate_indicators(klines)
    if not indicators:
        return f"⚪ {symbol.replace('-USDT','')}: Нет данных индикаторов"
    fib_levels = calculate_fibonacci_levels(indicators["close_series"])

    price = indicators["close"]
    macd = indicators["macd"]
    macd_signal = indicators["macd_signal"]
    rsi = indicators["rsi"]
    wr = indicators["wr"]
    volume = indicators["volume"]
    volume_prev = indicators["volume_previous"]
    ema = indicators["ema"]
    ema_prev = indicators["ema_previous"]

    vol_up = volume_trending_up(volume, volume_prev)

    # Лонг сигнал - касание уровня Фибо + индикаторы в зоне перепроданности и растущий объём
    for level_name, level_price in fib_levels.items():
        if price_touching_level(price, level_price):
            # Условия для Лонга
            if (macd > macd_signal and rsi < 40 and wr < -80 and vol_up and ema > ema_prev):
                tp = round(price * 1.03, 5)
                sl = round(price * 0.97, 5)
                msg = (f"🟢 {symbol.replace('-USDT','')}: Лонг от FIB {level_name} (цена {price})\n"
                       f"TP: {tp}, SL: {sl}\n"
                       f"MACD: {macd:.5f} > {macd_signal:.5f}\n"
                       f"RSI: {rsi:.1f} | WR: {wr:.1f}\n"
                       f"Объём: {'растёт' if vol_up else 'падает'}")
                return msg
            # Условия для Шорта
            if (macd < macd_signal and rsi > 60 and wr > -20 and vol_up and ema < ema_prev):
                tp = round(price * 0.97, 5)
                sl = round(price * 1.03, 5)
                msg = (f"🔴 {symbol.replace('-USDT','')}: Шорт от FIB {level_name} (цена {price})\n"
                       f"TP: {tp}, SL: {sl}\n"
                       f"MACD: {macd:.5f} < {macd_signal:.5f}\n"
                       f"RSI: {rsi:.1f} | WR: {wr:.1f}\n"
                       f"Объём: {'растёт' if vol_up else 'падает'}")
                return msg

    # Если сигналов нет — просто показать текущую цену
    return (f"⚪ {symbol.replace('-USDT','')}: Пока нет сигнала. Цена: {price}")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, data=payload)
        if not response.ok:
            print(f"Ошибка отправки Telegram-сообщения: {response.text}")
    except Exception as e:
        print(f"Ошибка запроса к Telegram API: {e}")

def job():
    for symbol in symbols:
        msg = get_signal(symbol)
        send_telegram_message(msg)

@app.route("/")
def index():
    return "CryptoFTW Bot is running."

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, 'interval', minutes=5)
    scheduler.start()
    # Запускаем первый запуск сразу
    job()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
