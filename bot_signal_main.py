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
import schedule  # <- добавляем schedule

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

symbols = ["BTC-USDT", "TIA-USDT", "PEOPLE-USDT", "POPCAT-USDT", "DOGE-USDT"]
base_url = "https://open-api.bingx.com"
headers = {"X-BX-APIKEY": API_KEY}

app = Flask(__name__)

last_sent_signals = {}  # Для фильтра от спама — хранит последний сигнал по каждой монете

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
        adx = ta.adx(df["high"], df["low"], df["close"], length=14).dropna()
        boll = ta.bbands(df["close"], length=20, std=2).dropna()

        # Фибоначчи на текущей цене (пример, можно расширить)
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
            "adx": adx["ADX_14"].iloc[-1],
            "boll_upper": boll["BBU_20_2.0"].iloc[-1],
            "boll_middle": boll["BBM_20_2.0"].iloc[-1],
            "boll_lower": boll["BBL_20_2.0"].iloc[-1],
            "price": df["close"].iloc[-1],
            "fibo_618": fibo_618,
            "fibo_5": fibo_5,
            "fibo_382": fibo_382
        }
    except Exception as e:
        send_telegram_message(f"Ошибка в расчете индикаторов: {e}")
        return None

def is_fibo_touch(price, fib_level, tolerance=0.002):  # tolerance - 0.2%
    return abs(price - fib_level) / fib_level < tolerance

def get_signal(symbol):
    klines = get_kline(symbol)
    if not klines or len(klines) < 50:
        return None  # Не присылаем спам, просто пропускаем

    indicators = calculate_indicators(klines)
    if not indicators:
        return None

    price = indicators["price"]
    fibo_touch = (
        is_fibo_touch(price, indicators["fibo_618"]) or
        is_fibo_touch(price, indicators["fibo_5"]) or
        is_fibo_touch(price, indicators["fibo_382"])
    )
    # Логика подтверждения по индикаторам + касание фибоначчи
    long_conditions = (
        indicators["macd"] > indicators["macd_signal"]
        and indicators["rsi"] < 50
        and indicators["wr"] < -80
        and indicators["volume"] > indicators["volume_prev"]
        and indicators["price"] > indicators["ema"]
        and indicators["adx"] > 20
        and fibo_touch
    )

    short_conditions = (
        indicators["macd"] < indicators["macd_signal"]
        and indicators["rsi"] > 60
        and indicators["wr"] > -20
        and indicators["volume"] > indicators["volume_prev"]
        and indicators["price"] < indicators["ema"]
        and indicators["adx"] > 20
        and fibo_touch
    )

    if long_conditions:
        tp = price + 1.5 * indicators["atr"]
        sl = price - 1 * indicators["atr"]
        return f"🟢 ЛОНГ {symbol.replace('-USDT','')}\nВход: {price:.4f}\nTP: {tp:.4f}, SL: {sl:.4f}"

    if short_conditions:
        tp = price - 1.5 * indicators["atr"]
        sl = price + 1 * indicators["atr"]
        return f"🔴 ШОРТ {symbol.replace('-USDT','')}\nВход: {price:.4f}\nTP: {tp:.4f}, SL: {sl:.4f}"

    return None  # Нет сигнала, не спамим

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
    global last_sent_signals
    for symbol in symbols:
        signal = get_signal(symbol)
        # Фильтр от спама — отправляем сообщение только если сигнал новый или изменился
        if signal and last_sent_signals.get(symbol) != signal:
            send_telegram_message(signal)
            last_sent_signals[symbol] = signal

def send_status_update():
    status = "Бот работает. Текущие цены:\n"
    for symbol in symbols:
        klines = get_kline(symbol)
        if klines:
            last_price = float(klines[-1]["close"])
            status += f"{symbol.replace('-USDT','')}: {last_price}\n"
    send_telegram_message(status)

def job_signals():
    check_signals()

def job_status():
    send_status_update()

def start_bot():
    # Запускаем расписание
    schedule.every(5).minutes.do(job_signals)
    schedule.every(30).minutes.do(job_status)

    # Первый запуск сразу, чтобы не ждать
    job_signals()
    job_status()

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=start_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
