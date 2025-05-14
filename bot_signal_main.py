import os
import time
import hmac
import hashlib
import requests

# Получение ключей из переменных окружения (Render)
API_KEY = os.environ.get('BINGX_API_KEY')
SECRET_KEY = os.environ.get('BINGX_API_SECRET')

# Список монет, которые ты отслеживаешь
symbols = ['BTC-USDT', 'ETH-USDT', 'TIA-USDT', 'POPCAT-USDT', 'PEOPLE-USDT']

# Базовый URL для получения цен
BASE_URL = 'https://open-api.bingx.com/openApi/swap/v2/quote/price'

def get_signature(params: dict, secret_key: str) -> str:
    # Склеиваем параметры без сортировки (по документации BingX)
    query = '&'.join([f'{key}={value}' for key, value in params.items()])
    return hmac.new(secret_key.encode(), query.encode(), hashlib.sha256).hexdigest()

def get_price(symbol: str):
    timestamp = str(int(time.time() * 1000))
    params = {
        'symbol': symbol,
        'timestamp': timestamp,
        'recvWindow': '5000'
    }
    # Подпись параметров
    signature = get_signature(params, SECRET_KEY)
    params['signature'] = signature

    headers = {
        'X-BX-APIKEY': API_KEY
    }

    try:
        response = requests.get(BASE_URL, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 0 and 'data' in data:
                return data['data']['price']
            else:
                print(f"[API ERROR] {symbol}: {data.get('msg')}")
        else:
            print(f"[HTTP ERROR] {symbol}: Status {response.status_code}")
    except Exception as e:
        print(f"[EXCEPTION] {symbol}: {e}")
    return None

def main():
    print("=== Актуальные цены на BingX ===")
    for symbol in symbols:
        price = get_price(symbol)
        if price:
            print(f"{symbol}: {price} USDT")
        else:
            print(f"{symbol}: не удалось получить цену")
        time.sleep(0.3)  # задержка, чтобы не спамить API

if __name__ == '__main__':
    main()
