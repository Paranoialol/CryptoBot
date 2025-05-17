# File: logic_of_analyze.py

import hmac
import hashlib
import requests
import pandas as pd
from urllib.parse import urlencode
from datetime import datetime

def send_debug_telegram(message, telegram_token, telegram_chat_id):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {
        "chat_id": telegram_chat_id,
        "text": f"🐞 DEBUG [{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}]:\n{message}",
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Ошибка отправки отладки в Telegram: {e}")

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
            return f"Ошибка API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Исключение при запросе: {e}"

def analyze(symbols, api_secret, headers, telegram_token, telegram_chat_id, base_url):
    intervals = ["1m", "5m", "15m", "1h"]

    for symbol in symbols:
        message = f"<b>📊 Проверка данных для {symbol}</b>:\n"
        for interval in intervals:
            klines = get_kline(symbol, interval, 5, api_secret, headers, base_url)

            if isinstance(klines, str):  # если вернулась ошибка
                message += f"{interval}: ❌ {klines}\n"
                continue

            if not klines:
                message += f"{interval}: ❌ Нет данных\n"
                continue

            try:
                df = pd.DataFrame(klines, columns=["open", "close", "high", "low", "volume", "time"])
                df = df.apply(pd.to_numeric, errors='ignore')
                first_rows = df.head(3).to_string(index=False)
                message += f"{interval}: ✅\n<pre>{first_rows}</pre>\n\n"
            except Exception as e:
                message += f"{interval}: ⚠️ Ошибка обработки данных: {e}\n"

        send_debug_telegram(message, telegram_token, telegram_chat_id)
