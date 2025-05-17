import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode
import logging
import os

import telegram

# Конфиги из env
API_KEY = os.getenv('BINGX_API_KEY')
API_SECRET = os.getenv('BINGX_API_SECRET')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

bot = telegram.Bot(token=TELEGRAM_TOKEN)

BASE_URL = 'https://open-api.bingx.com'
KLINES_PATH = '/openApi/swap/v3/quote/klines'

# Таймфреймы, которые анализируем
TIMEFRAMES = ['1m', '5m', '15m', '1h']

def send_telegram_message(text):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
    except Exception as e:
        print(f"Telegram send error: {e}")

def sign_request(params, secret):
    query_string = urlencode(sorted(params.items()))
    signature = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    return signature

def fetch_klines(symbol, interval, limit=100):
    timestamp = int(time.time() * 1000)
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit,
        'timestamp': str(timestamp)
    }
    params['signature'] = sign_request(params, API_SECRET)

    headers = {
        'X-BX-APIKEY': API_KEY
    }

    try:
        response = requests.get(BASE_URL + KLINES_PATH, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('success', False) or data.get('code') == '00000':  # разные варианты ответа
            return data.get('data', [])
        else:
            send_telegram_message(f"❌ Ошибка API для {symbol} {interval}: {data}")
            return []
    except Exception as e:
        send_telegram_message(f"❌ Ошибка запроса данных для {symbol} {interval}: {e}")
        return []

def analyze_symbol(symbol):
    debug_text = [f"📊 Проверка данных для {symbol}:"]
    for tf in TIMEFRAMES:
        klines = fetch_klines(symbol, tf)
        if not klines:
            debug_text.append(f"{tf}: ❌ Нет данных")
        else:
            # Отобразим 3 последних свечи в упрощенном виде
            sample_data = []
            for k in klines[:3]:
                sample_data.append(
                    f"open={k['open']} close={k['close']} high={k['high']} low={k['low']} volume={k['volume']} time={k['time']}"
                )
            debug_text.append(f"{tf}: ✅\n  " + "\n  ".join(sample_data))
    send_telegram_message("\n".join(debug_text))


if __name__ == "__main__":
    symbols = ["BTC-USDT", "TIA-USDT", "PEOPLE-USDT", "POPCAT-USDT", "DOGE-USDT"]
    for s in symbols:
        analyze_symbol(s)
        time.sleep(1)  # пауза, чтобы не забанили по лимитам
