import os
import time
import requests
import hmac
import hashlib
import logging
import pandas as pd

# Настройка логгирования
logging.basicConfig(level=logging.INFO)

# Получаем ключи из переменных окружения
API_KEY = os.environ.get("BINGX_API_KEY")
API_SECRET = os.environ.get("BINGX_API_SECRET")

# Параметры
SYMBOLS = ['BTC-USDT', 'ETH-USDT', 'PEOPLE-USDT', 'DOGE-USDT']
INTERVAL = '1m'
LIMIT = 100
BASE_URL = "https://open-api.bingx.com"

# Функция генерации подписи
def sign(params: dict, secret_key: str):
    sorted_params = sorted(params.items())
    encoded = "&".join([f"{k}={v}" for k, v in sorted_params])
    signature = hmac.new(secret_key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return signature

# Функция получения свечей (Klines)
def get_klines(symbol):
    endpoint = "/openApi/futures/market/kline"
    url = BASE_URL + endpoint
    timestamp = int(time.time() * 1000)
    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": LIMIT,
        "timestamp": timestamp
    }
    params["signature"] = sign(params, API_SECRET)
    headers = {
        "X-BX-APIKEY": API_KEY
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        candles = data.get("data", [])
        if not candles:
            logging.warning(f"Пустые данные по {symbol}")
            return None
        df = pd.DataFrame(candles)
        df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'count', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore']
        df['close'] = df['close'].astype(float)
        return df
    except Exception as e:
        logging.warning(f"Ошибка запроса {symbol}: {e}")
        return None

# Основной цикл
def main():
    for symbol in SYMBOLS:
        df = get_klines(symbol)
        if df is not None:
            logging.info(f"Последняя свеча по {symbol}: {df.iloc[-1]['close']}")

if __name__ == "__main__":
    main()
