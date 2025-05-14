import time
import hashlib
import hmac
import os
import requests

# Получаем ключи из переменных окружения
API_KEY = os.getenv('BINGX_API_KEY')  # API_KEY
API_SECRET = os.getenv('BINGX_API_SECRET')  # API_SECRET

# URL для API
url = 'https://api.bingx.com/api/v1/futures/market/candles'

# Параметры запроса
params = {
    'symbol': 'btcusdt',  # Символ монеты
    'interval': '1m',     # Интервал
    'limit': 100          # Лимит данных
}

# Время запроса в миллисекундах
timestamp = str(int(time.time() * 1000))

# Формируем строку для подписи
query_string = f"symbol={params['symbol']}&interval={params['interval']}&limit={params['limit']}&timestamp={timestamp}"

# Подпись
signature = hmac.new(
    API_SECRET.encode('utf-8'),
    query_string.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# Заголовки с API ключом и подписью
headers = {
    'X-BX-APIKEY': API_KEY  # Используем API ключ в заголовке
}

# Добавляем подпись в параметры запроса
params['timestamp'] = timestamp
params['signature'] = signature

# Отправляем запрос
response = requests.get(url, params=params, headers=headers)

if response.status_code == 200:
    print(response.json())  # Выводим результат
else:
    print(f"Error: {response.status_code} - {response.text}")
