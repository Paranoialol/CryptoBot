import requests
import pandas as pd
from datetime import datetime
from urllib.parse import urlencode
import hmac
import hashlib

def sign_request(params, api_secret):
    query = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
    signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

def get_kline(symbol, interval, limit, api_secret, headers, base_url):
    path = '/openApi/swap/v3/quote/klines'
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "timestamp": str(int(datetime.utcnow().timestamp() * 1000))
    }
    try:
        signed_params = sign_request(params, api_secret)
        url = f"{base_url}{path}?{urlencode(signed_params)}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("data", [])
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Exception fetching kline for {symbol} ({interval}): {e}")
    return []

def send_telegram_message(message, telegram_token, telegram_chat_id):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {
        "chat_id": telegram_chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print(f"Ошибка отправки сообщения: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Ошибка Telegram: {e}")

def analyze(symbols, api_secret, headers, telegram_token, telegram_chat_id, base_url):
    intervals = {
        "1m": "1",
        "5m": "5",
        "15m": "15",
        "1h": "60"
    }

    for symbol in symbols:
        message = f"📊 Данные для <b>{symbol}</b> ({datetime.utcnow().strftime('%H:%M:%S UTC')}):\n\n"

        for interval_name, interval_val in intervals.items():
            klines = get_kline(symbol, interval_val, 100, api_secret, headers, base_url)

            if not klines:
                message += f"{interval_name}: Нет данных.\n\n"
                continue

            df = pd.DataFrame(klines)
            df.columns = ["open", "close", "high", "low", "volume", "time"]

            # Выведем первые 5 строк с ключевыми колонками
            sample = df.head(5).to_string(index=False)

            message += f"{interval_name} (первые 5 строк):\n{sample}\n\n"

        send_telegram_message(message, telegram_token, telegram_chat_id)
