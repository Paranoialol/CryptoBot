import os
import time
import hmac
import hashlib
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import pandas_ta as ta

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "X-BX-APIKEY": API_KEY
}

SYMBOLS = ["BTC-USDT", "TIA-USDT", "PEOPLE-USDT", "POPCAT-USDT", "DOGE-USDT"]
INTERVAL = "1m"

FIB_LEVELS = [0.382, 0.5, 0.618]

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    requests.post(url, data=data)

def sign(params):
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    signature = hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    return signature

def get_klines(symbol, interval, limit=100):
    url = "https://open-api.bingx.com/openApi/spot/v1/market/kline"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    params["timestamp"] = int(time.time() * 1000)
    params["signature"] = sign(params)
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        data = response.json()
        if data['code'] == 0 and 'data' in data:
            return pd.DataFrame(data['data'])
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
    return pd.DataFrame()

def analyze():
    for symbol in SYMBOLS:
        df = get_klines(symbol, INTERVAL)
        if df.empty or len(df) < 50:
            send_telegram_message(f"⚪ {symbol.split('-')[0]}: Недостаточно данных для анализа")
            continue

        df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        df['close'] = df['close']

        close = df['close']
        volume = df['volume']

        ema = ta.ema(close, length=20).iloc[-1]
        macd_line, signal_line = ta.macd(close).iloc[-1][['MACD_12_26_9', 'MACDs_12_26_9']]
        rsi = ta.rsi(close, length=14).iloc[-1]
        wr = ta.willr(df['high'], df['low'], close).iloc[-1]
        atr = ta.atr(df['high'], df['low'], close, length=14).iloc[-1]

        price = close.iloc[-1]
        prev_volume = volume.iloc[-2]
        current_volume = volume.iloc[-1]
        vol_status = "растёт" if current_volume > prev_volume else "падает"

        fib_min = close.min()
        fib_max = close.max()
        fib_0382 = fib_max - (fib_max - fib_min) * 0.382
        fib_050 = fib_max - (fib_max - fib_min) * 0.5
        fib_0618 = fib_max - (fib_max - fib_min) * 0.618

        signal = ""
        emoji = "⚪"
        tp = round(price + 2 * atr, 4)
        sl = round(price - 2 * atr, 4)

        if abs(price - fib_050) / price < 0.003:
            if macd_line > signal_line and rsi > 38 and wr < -80:
                signal = f"Лонг от FIB 0.5 ({price})"
                emoji = "🟢"
            elif macd_line < signal_line and rsi < 62 and wr > -20:
                signal = f"Шорт от FIB 0.5 ({price})"
                emoji = "🔴"
        elif abs(price - fib_0618) / price < 0.003:
            if macd_line > signal_line and rsi > 38 and wr < -80:
                signal = f"Лонг от FIB 0.618 ({price})"
                emoji = "🟢"
            elif macd_line < signal_line and rsi < 62 and wr > -20:
                signal = f"Шорт от FIB 0.618 ({price})"
                emoji = "🔴"

        message = f"{emoji} {symbol.split('-')[0]}: {signal if signal else 'Пока нет сигнала'}"
        if signal:
            message += f"\nTP: {tp}, SL: {sl}"
        message += f"\nMACD: {round(macd_line, 4)} {'>' if macd_line > signal_line else '<'} {round(signal_line, 4)}"
        message += f"\nRSI: {round(rsi, 2)} | WR: {round(wr, 2)}"
        message += f"\nОбъём: {vol_status}"

        send_telegram_message(message)

scheduler = BackgroundScheduler()
scheduler.add_job(analyze, 'interval', minutes=5)
scheduler.start()

@app.route('/')
def index():
    return "Crypto Signal Bot is running."

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
