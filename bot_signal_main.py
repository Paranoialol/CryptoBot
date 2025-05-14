import logging
import os
import time
import requests
import pandas as pd
from telegram import Bot
from ta.momentum import RSIIndicator, WilliamsRIndicator
from ta.trend import MACD

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_CHAT_ID = os.getenv("USER_CHAT_ID")
SYMBOLS = ["DOGE-USDT", "PEPE-USDT", "PEOPLE-USDT", "BTC-USDT", "ETH-USDT"]
INTERVAL = "1m"
LIMIT = 100
BASE_URL = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"

bot = Bot(token=TELEGRAM_TOKEN)
logging.basicConfig(level=logging.INFO)

def get_klines(symbol):
    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": LIMIT
    }
    try:
        res = requests.get(BASE_URL, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        if not data:
            logging.warning(f"Ошибка запроса {symbol}: Пустые данные")
            return None
        df = pd.DataFrame(data)
        df.columns = [
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_vol", "taker_buy_quote_vol", "ignore"
        ]
        df["close"] = pd.to_numeric(df["close"])
        df["high"] = pd.to_numeric(df["high"])
        df["low"] = pd.to_numeric(df["low"])
        return df
    except requests.exceptions.RequestException as e:
        logging.warning(f"Ошибка запроса {symbol}: {e}")
        return None

def analyze(df):
    df["rsi"] = RSIIndicator(df["close"]).rsi()
    df["wr"] = WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r()
    macd = MACD(close=df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

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

def format_message(symbol, signal, data):
    entry = round(float(data["close"]), 6)
    tp = round(entry * (1.02 if signal == "LONG" else 0.98), 6)
    sl = round(entry * (0.99 if signal == "LONG" else 1.01), 6)
    direction = "вверх" if data["macd"] > data["macd_signal"] else "вниз"
    
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

def main_loop():
    while True:
        for symbol in SYMBOLS:
            df = get_klines(symbol)
            if df is not None:
                signal, data = analyze(df)
                if signal:
                    message = format_message(symbol, signal, data)
                    bot.send_message(chat_id=USER_CHAT_ID, text=message)
        time.sleep(300)  # каждые 5 минут

if __name__ == "__main__":
    main_loop()
