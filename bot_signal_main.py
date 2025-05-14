import os
import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode

# Получаем API-ключ и секретный ключ из переменных среды
API_KEY = os.getenv('BINGX_API_KEY')
API_SECRET = os.getenv('BINGX_API_SECRET')

# Убедись, что переменные установлены корректно
if not API_KEY or not API_SECRET:
    raise ValueError("API-ключ и секретный ключ не установлены в переменных среды.")

BASE_URL = 'https://api.bingx.com/api/v1/futures/market/candles'

# Формируем параметры для запроса
params = {
    'symbol': 'BTC-USDT',
    'interval': '1m',
    'limit': 100
}

# Добавляем параметры в запрос
query_string = urlencode(params)

# Получаем текущую метку времени в миллисекундах
timestamp = str(int(time.time() * 1000))  # Текущая метка времени в миллисекундах
params['timestamp'] = timestamp

# Создаем строку запроса для подписи
signature_payload = urlencode(params)

# Создаем подпись с использованием секретного ключа
signature = hmac.new(API_SECRET.encode('utf-8'), signature_payload.encode('utf-8'), hashlib.sha256).hexdigest()

# Добавляем подпись в параметры запроса
params['signature'] = signature

# Заголовки для аутентификации
headers = {
    'X-BINGX-API-KEY': API_KEY
}

# Выполним запрос с аутентификацией
response = requests.get(BASE_URL, headers=headers, params=params)

# Проверяем результат
if response.status_code == 200:
    print("Ответ:", response.json())
else:
    print(f"Ошибка: {response.status_code}")
    print(response.text)
