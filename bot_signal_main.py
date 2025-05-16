import os
import time
import threading
from flask import Flask
from datetime import datetime
from logic_of_analyze import analyze  # импортируем функцию анализа из второго файла

# API ключи из переменных окружения
API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

symbols = ["BTC-USDT", "TIA-USDT", "PEOPLE-USDT", "POPCAT-USDT", "DOGE-USDT"]
base_url = "https://open-api.bingx.com"
headers = {"X-BX-APIKEY": API_KEY}

app = Flask(__name__)
bot_started = False

def run_bot():
    global bot_started
    if bot_started:
        return
    bot_started = True

    def loop():
        while True:
            analyze(symbols, API_SECRET, headers, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, base_url)
            time.sleep(300)  # каждые 5 минут

    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()

@app.route("/")
def home():
    if not bot_started:
        run_bot()
    return "Бот запущен и работает!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
