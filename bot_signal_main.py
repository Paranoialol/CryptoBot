import requests

# ВСТАВЬ СЮДА СВОЙ ТОКЕН от BotFather
TELEGRAM_TOKEN = "8031738383:AAE3zxHvhSFhbTESh0dxEPaoODCrPnuOIxw"

# ВСТАВЬ СЮДА СВОЙ chat_id, например: "123456789"
TELEGRAM_CHAT_ID = "557172438"

TEXT = "Привет! Это тестовое сообщение от моего CryptoBot."

def send_test_message():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": TEXT
    }

    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print("Сообщение успешно отправлено!")
        print("Ответ Telegram:", response.text)
    except requests.exceptions.RequestException as e:
        print("Ошибка при отправке сообщения:", e)
        print("Код ответа:", response.status_code)
        print("Ответ Telegram:", response.text)

send_test_message()
