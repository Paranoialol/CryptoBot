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
    except Exception:
        return []

def calculate_indicators(klines):
    df = pd.DataFrame(klines)
    df["close"] = df["close"].astype(float)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df.dropna(inplace=True)

    if len(df) < 50:
        return None

    try:
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9).dropna()
        rsi = ta.rsi(df["close"], length=14).dropna()
        ema = ta.ema(df["close"], length=21).dropna()
        bbands = ta.bbands(df["close"], length=20, std=2).dropna()
        stoch = ta.stoch(df["high"], df["low"], df["close"], fastk=14, slowk=3, slowd=3).dropna()
        wr = ta.willr(df["high"], df["low"], df["close"], length=14).dropna()

        high_max = df["high"].tail(50).max()
        low_min = df["low"].tail(50).min()
        last_close = df["close"].iloc[-1]

        fib_0_382 = low_min + 0.382 * (high_max - low_min)
        fib_0_5 = low_min + 0.5 * (high_max - low_min)
        fib_0_618 = low_min + 0.618 * (high_max - low_min)

        atr = ta.atr(df["high"], df["low"], df["close"], length=14).dropna()

        return {
            "macd": macd["MACD_12_26_9"].iloc[-1],
            "macd_signal": macd["MACDs_12_26_9"].iloc[-1],
            "rsi": rsi.iloc[-1],
            "ema": ema.iloc[-1],
            "ema_previous": ema.iloc[-2] if len(ema) > 1 else ema.iloc[-1],
            "upperband": bbands["BBU_20_2.0"].iloc[-1],
            "lowerband": bbands["BBL_20_2.0"].iloc[-1],
            "slowk": stoch["STOCHk_14_3_3"].iloc[-1],
            "slowd": stoch["STOCHd_14_3_3"].iloc[-1],
            "wr": wr.iloc[-1],
            "volume": df["volume"].iloc[-1],
            "volume_previous": df["volume"].iloc[-2] if len(df) > 1 else df["volume"].iloc[-1],
            "fib_levels": (fib_0_382, fib_0_5, fib_0_618),
            "last_close": last_close,
            "atr": atr.iloc[-1]
        }
    except Exception:
        return None

def get_signal(symbol):
    klines = get_kline(symbol)
    if len(klines) >= 50:
        ind = calculate_indicators(klines)
        if not ind:
            return f"⚠️ {symbol.replace('-USDT','')}: Недостаточно данных"

        signal_details = (
            f"{symbol}: MACD={round(ind['macd'],3)} vs Signal={round(ind['macd_signal'],3)}, "
            f"RSI={round(ind['rsi'],1)}, WR={round(ind['wr'],1)}, Vol={round(ind['volume'],1)} vs Prev={round(ind['volume_previous'],1)}, "
            f"EMA={round(ind['ema'],3)} vs Prev EMA={round(ind['ema_previous'],3)}, Close={round(ind['last_close'],3)}"
        )

        # Лонг
        if (
            ind["macd"] > ind["macd_signal"] and
            40 < ind["rsi"] < 60 and
            ind["wr"] < -80 and
            ind["volume"] > ind["volume_previous"] and
            ind["last_close"] > ind["fib_levels"][1] and
            ind["ema"] > ind["ema_previous"]
        ):
            tp = round(ind["last_close"] + ind["atr"] * 1.5, 5)
            sl = round(ind["last_close"] - ind["atr"] * 1.0, 5)
            return f"🔵 {symbol.replace('-USDT','')}: Лонг\nTP: {tp}, SL: {sl}\n{signal_details}"

        # Шорт
        elif (
            ind["macd"] < ind["macd_signal"] and
            40 < ind["rsi"] < 60 and
            ind["wr"] > -20 and
            ind["volume"] > ind["volume_previous"] and
            ind["last_close"] < ind["fib_levels"][1] and
            ind["ema"] < ind["ema_previous"]
        ):
            tp = round(ind["last_close"] - ind["atr"] * 1.5, 5)
            sl = round(ind["last_close"] + ind["atr"] * 1.0, 5)
            return f"🔴 {symbol.replace('-USDT','')}: Шорт\nTP: {tp}, SL: {sl}\n{signal_details}"

        return f"⚪ {symbol.replace('-USDT','')}: Нет сигнала\n{signal_details}"
    return f"⚠️ {symbol.replace('-USDT','')}: Нет данных"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

def check_signals():
    for symbol in symbols:
        signal = get_signal(symbol)
        send_telegram_message(signal)

def send_status_update():
    status_message = "Я работаю, мой господин. Текущие цены:\n"
    for symbol in symbols:
        klines = get_kline(symbol)
        if klines:
            last_price = klines[-1]["close"]
            status_message += f"{symbol.replace('-USDT','')}: {last_price}\n"
    send_telegram_message(status_message)

def start_bot():
    global bot_started
    if not bot_started:
        bot_started = True
        check_signals()
        send_status_update()
        while True:
            time.sleep(30 * 60)
            check_signals()
            send_status_update()

if __name__ == "__main__":
    start_bot()
    
