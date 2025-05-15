import os
import requests
import pandas as pd
import pandas_ta as ta
import numpy as np
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from dotenv import load_dotenv
from candlestick import candlestick

load_dotenv()

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

symbol = "1000PEOPLEUSDT"
interval = "1m"
limit = 100

scheduler = BackgroundScheduler()
scheduler.start()

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Telegram: {e}")

def fetch_klines(symbol, interval, limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        print(f"Ошибка при получении данных с Binance: {e}")
        return None

def calculate_indicators(df):
    try:
        df['ema20'] = ta.ema(df['close'], length=20)
        df['ema50'] = ta.ema(df['close'], length=50)
        macd = ta.macd(df['close'])
        df['macd'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['wr'] = ta.williams_r(df['high'], df['low'], df['close'], lbp=14)

        # Добавление свечных паттернов
        df = candlestick.bullish_engulfing(df)
        df = candlestick.bearish_engulfing(df)
        df = candlestick.hammer(df)
        df = candlestick.shooting_star(df)

        return {
            "macd": df["macd"].iloc[-1],
            "macd_signal": df["macd_signal"].iloc[-1],
            "rsi": df["rsi"].iloc[-1],
            "wr": df["wr"].iloc[-1],
            "ema20": df["ema20"].iloc[-1],
            "ema50": df["ema50"].iloc[-1],
            "volume": df["volume"].iloc[-1],
            "close": df["close"].iloc[-1],
            "bullish_engulfing": df["bullish_engulfing"].iloc[-1],
            "bearish_engulfing": df["bearish_engulfing"].iloc[-1],
            "hammer": df["hammer"].iloc[-1],
            "shooting_star": df["shooting_star"].iloc[-1]
        }
    except Exception as e:
        send_telegram_message(f"Ошибка при расчете индикаторов: {e}")
        return None

def generate_signal_message(ind):
    try:
        msg = f"📊 *Анализ {symbol} ({interval})*"

        msg += f"Цена: `{ind['close']:.4f}`\n"
        msg += f"EMA20: `{ind['ema20']:.4f}` | EMA50: `{ind['ema50']:.4f}`\n"
        msg += f"MACD: `{ind['macd']:.4f}` | Signal: `{ind['macd_signal']:.4f}`\n"
        msg += f"RSI: `{ind['rsi']:.2f}` | WR: `{ind['wr']:.2f}`\n"
        msg += f"Volume: `{ind['volume']:.2f}`"

        # Добавим паттерны, если есть
        patterns = []
        if ind['bullish_engulfing']:
            patterns.append("📈 *Bullish Engulfing*")
        if ind['bearish_engulfing']:
            patterns.append("📉 *Bearish Engulfing*")
        if ind['hammer']:
            patterns.append("🔨 *Hammer*")
        if ind['shooting_star']:
            patterns.append("🌠 *Shooting Star*")

        if patterns:
            msg += "\n\n🧠 Обнаружены паттерны:\n" + "\n".join(patterns)

        return msg
    except Exception as e:
        return f"Ошибка при генерации сообщения: {e}"

def analyze():
    df = fetch_klines(symbol, interval, limit)
    if df is not None:
        indicators = calculate_indicators(df)
        if indicators:
            message = generate_signal_message(indicators)
            send_telegram_message(message)

scheduler.add_job(analyze, 'interval', minutes=5)

@app.route('/')
def index():
    return "Бот запущен и работает."

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
