import os
import time
import hmac
import hashlib
import threading
import requests
import json
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

def get_kline(symbol, interval="1m", limit=2):
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
        data = res.json().get("data", [])
        print(f"[API Response] {symbol}: {data}")
        return data
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
                prices = get_price_change(symbol)
                if "данных нет" not in prices:
                    send_telegram_message(prices)  # Если есть данные — отправляем в Telegram
                    any_signals = True
            except Exception as e:
                print(f"[Ошибка при анализе {symbol}] {e}")
        if not any_signals:
            msg = "Бот работает. Пока точек входа не найдено.\nТекущие цены:\n" + "\n".join([get_price_change(sym) for sym in symbols])
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
