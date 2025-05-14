import logging import os import time import hmac import hashlib import requests import pandas as pd from telegram import Bot from ta.momentum import RSIIndicator, WilliamsRIndicator from ta.trend import MACD

Настройки

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") USER_CHAT_ID = os.getenv("USER_CHAT_ID") API_KEY = os.getenv("BINGX_API_KEY") API_SECRET = os.getenv("BINGX_API_SECRET") SYMBOLS = ["BTC-USDT", "ETH-USDT", "DOGE-USDT", "PEPE-USDT", "PEOPLE-USDT"] INTERVAL = "1m" LIMIT = 100 BASE_URL = "https://open-api.bingx.com/openApi/swap/v2/quote/kline"

bot = Bot(token=TELEGRAM_TOKEN) logging.basicConfig(level=logging.INFO)

def sign_request(params, secret): query = "&".join([f"{key}={params[key]}" for key in sorted(params)]) signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest() return signature

def get_klines(symbol): params = { "symbol": symbol, "interval": INTERVAL, "limit": LIMIT, "timestamp": str(int(time.time() * 1000)) } params["signature"] = sign_request(params, API_SECRET) headers = { "X-BX-APIKEY": API_KEY } res = requests.get(BASE_URL, headers=headers, params=params) if res.status_code != 200: logging.warning(f"Ошибка запроса {symbol}: {res.status_code} {res.text}") return None data = res.json().get("data") if not data: logging.warning(f"Пустые данные: {symbol}") return None df = pd.DataFrame(data) if df.shape[1] == 6: df.columns = ["timestamp", "open", "high", "low", "close", "volume"] df["close"] = pd.to_numeric(df["close"]) df["high"] = pd.to_numeric(df["high"]) df["low"] = pd.to_numeric(df["low"]) return df return None

def analyze(df): df["rsi"] = RSIIndicator(df["close"]).rsi() df["wr"] = WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r() macd = MACD(close=df["close"]) df["macd"] = macd.macd() df["macd_signal"] = macd.macd_signal()

latest = df.iloc[-1]
prev = df.iloc[-2]

signal = None
if (
    latest["rsi"] > 45 and latest["rsi"] < 65 and
    latest["wr"] > -80 and latest["wr"] < -20 and
    latest["macd"] > latest["macd_signal"] and
    prev["macd"] < prev["macd_signal"]
):
    signal = "LONG"
elif (
    latest["rsi"] < 55 and latest["rsi"] > 35 and
    latest["wr"] < -20 and
    latest["macd"] < latest["macd_signal"] and
    prev["macd"] > prev["macd_signal"]
):
    signal = "SHORT"
return signal, latest

def format_message(symbol, signal, data): entry = round(float(data["close"]), 6) tp = round(entry * (1.02 if signal == "LONG" else 0.98), 6) sl = round(entry * (0.99 if signal == "LONG" else 1.01), 6) direction = "вверх" if data["macd"] > data["macd_signal"] else "вниз"

msg = (
    f"Монета: {symbol.replace('-USDT', '')}\n"
    f"Сигнал: {signal}\n"
    f"Цена входа: {entry}\n"
    f"TP: {tp} | SL: {sl}\n"
    f"MACD: {direction}\n"
    f"RSI: {round(data['rsi'], 2)}\n"
    f"WR: {round(data['wr'], 2)}"
)
return msg

def main_loop(): while True: for symbol in SYMBOLS: df = get_klines(symbol) if df is not None: signal, data = analyze(df) if signal: message = format_message(symbol, signal, data) bot.send_message(chat_id=USER_CHAT_ID, text=message) time.sleep(300)  # каждые 5 минут

if name == "main": main_loop()
