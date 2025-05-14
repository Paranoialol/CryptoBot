import os
import time
import hmac
import hashlib
import requests
import json
import pandas as pd
from dotenv import load_dotenv
from ta.momentum import RSIIndicator, WilliamsRIndicator
from ta.trend import MACD, EMAIndicator

load_dotenv()

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = "8031738383:AAE3zxHvhSFhbTESh0dxEPaoODCrPnuOIxw"
TELEGRAM_CHAT_ID = "557172438"

symbols = ["BTC-USDT", "TIA-USDT", "PEOPLE-USDT", "POPCAT-USDT", "DOGE-USDT"]
base_url = "https://open-api.bingx.com/openApi/swap/quote/v1/kline"

headers = {
    "X-BX-APIKEY": API_KEY
}

def sign_request(params):
    query = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

def get_kline(symbol):
    params = {
        "symbol": symbol,
        "interval": "1m",
        "limit": 100
    }
    signed = sign_request(params.copy())
    res = requests.get(base_url, headers=headers, params=signed)
    return res.json()["data"]

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
    close = df["close"].astype(float)
    resistance = max(high[-20:])
    support = min(low[-20:])
    return resistance, support

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    requests.post(url, data=payload)

def analyze_symbol(symbol):
    raw = get_kline(symbol)
    df = pd.DataFrame(raw)
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df = df.astype(float)

    macd, rsi, wr, ema = get_indicators(df)
    resistance, support = get_levels(df)
    last_price = float(df["close"].iloc[-1])
    signal = None

    if macd > 0 and rsi > 45 and wr > -80 and last_price > ema:
        signal = "ЛОНГ"
        tp = resistance
        sl = support
    elif macd < 0 and rsi < 55 and wr < -20 and last_price < ema:
        signal = "ШОРТ"
        tp = support
        sl = resistance

    if signal:
        msg = (
            f"Монета: {symbol.replace('-USDT','')}\n"
            f"Сигнал: {signal}\n"
            f"Цена входа: {last_price:.2f}\n"
            f"TP: {tp:.2f}\n"
            f"SL: {sl:.2f}\n"
            f"MACD: {macd:.4f}, RSI: {rsi:.2f}, WR: {wr:.2f}, EMA: {ema:.2f}"
        )
        send_telegram_message(msg)

if __name__ == "__main__":
    while True:
        for symbol in symbols:
            try:
                analyze_symbol(symbol)
            except Exception as e:
                print(f"Ошибка для {symbol}: {e}")
        time.sleep(300)  # каждые 5 минут
