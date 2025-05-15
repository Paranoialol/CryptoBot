import os
import time
import hmac
import hashlib
import threading
import requests
import pandas as pd
import pandas_ta as ta
from urllib.parse import urlencode
from flask import Flask

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

def get_kline(symbol, interval="1m", limit=200):
    path = '/openApi/swap/v3/quote/klines'
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
        response_data = res.json()
        if 'data' in response_data and response_data['data']:
            return response_data['data']
    except Exception as e:
        send_telegram_message(f"Ошибка при получении свечей {symbol}: {e}")
    return []

def calculate_indicators(klines):
    df = pd.DataFrame(klines)
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)

    if len(df) < 50:
        return None

    try:
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9).dropna()
        rsi = ta.rsi(df["close"], length=14).dropna()
        ema = ta.ema(df["close"], length=21).dropna()
        wr = ta.willr(df["high"], df["low"], df["close"], length=14).dropna()
        atr = ta.atr(df["high"], df["low"], df["close"], length=14).dropna()

        fibo_618 = df["close"].iloc[-1] * 0.618
        fibo_5 = df["close"].iloc[-1] * 0.5
        fibo_382 = df["close"].iloc[-1] * 0.382

        return {
            "macd": macd["MACD_12_26_9"].iloc[-1],
            "macd_signal": macd["MACDs_12_26_9"].iloc[-1],
            "rsi": rsi.iloc[-1],
            "wr": wr.iloc[-1],
            "ema": ema.iloc[-1],
            "ema_prev": ema.iloc[-2] if len(ema) > 1 else ema.iloc[-1],
            "volume": df["volume"].iloc[-1],
            "volume_prev": df["volume"].iloc[-2] if len(df) > 1 else df["volume"].iloc[-1],
            "atr": atr.iloc[-1],
            "price": df["close"].iloc[-1],
            "fibo_618": fibo_618,
            "fibo_5": fibo_5,
            "fibo_382": fibo_382
        }
    except Exception as e:
        send_telegram_message(f"Ошибка в расчете индикаторов: {e}")
        return None

def get_signal(symbol):
    klines = get_kline(symbol)
    if not klines or len(klines) < 50:
        return None

    indicators = calculate_indicators(klines)
    if not indicators:
        return None

    price = indicators["price"]
    ema = indicators["ema"]
    ema_prev = indicators["ema_prev"]
    macd = indicators["macd"]
    macd_signal = indicators["macd_signal"]
    rsi = indicators["rsi"]
    wr = indicators["wr"]
    volume = indicators["volume"]
    volume_prev = indicators["volume_prev"]
    atr = indicators["atr"]

    # Определяем тренд по EMA и его направлению
    if price > ema:
        trend = "восходящий"
    else:
        trend = "нисходящий"

    # Дополнительно смотрим, растёт EMA или падает
    ema_trend = "растёт" if ema > ema_prev else "снижается"

    # Объёмы: растут или падают
    volume_trend = "растут" if volume > volume_prev else "снижаются"

    # MACD сигнал
    if macd > macd_signal:
        macd_trend = "бычий импульс"
    elif macd < macd_signal:
        macd_trend = "медвежий импульс"
    else:
        macd_trend = "нейтральный импульс"

    # RSI — зоны
    if rsi > 70:
        rsi_zone = "перекупленность"
    elif rsi < 30:
        rsi_zone = "перепроданность"
    else:
        rsi_zone = "нейтральная зона"

    # WR — зоны
    if wr > -20:
        wr_zone = "перекупленность"
    elif wr < -80:
        wr_zone = "перепроданность"
    else:
        wr_zone = "нейтральная зона"

    # Фибо зона
    if price > indicators["fibo_5"]:
        fibo_zone = "Цена выше уровня 0.5 по Фибоначчи — возможен потенциал роста."
    else:
        fibo_zone = "Цена ниже уровня 0.5 по Фибоначчи — возможно давление продавцов."

    msg = f"Монета *{symbol.replace('-USDT','')}*\n"
    msg += f"Текущая цена: {price:.4f} USDT\n"
    msg += f"Тренд: {trend} (EMA 21 {ema_trend})\n"
    msg += f"Объёмы {volume_trend}, что говорит о {'возрастающем интересе' if volume > volume_prev else 'снижении активности'}\n"
    msg += f"MACD: {macd:.4f} ({macd_trend})\n"
    msg += f"RSI: {rsi:.2f} ({rsi_zone})\n"
    msg += f"Williams %R: {wr:.2f} ({wr_zone})\n"
    msg += f"{fibo_zone}\n"

    # Условия на вход в лонг
    long_conditions = (
        macd > macd_signal
        and rsi < 50
        and wr < -80
        and volume > volume_prev
        and price > ema
    )

    # Условия на вход в шорт
    short_conditions = (
        macd < macd_signal
        and rsi > 60
        and wr > -20
        and volume > volume_prev
        and price < ema
    )

    if long_conditions:
        tp = price + 1.5 * atr
        sl = price - 1 * atr
        msg += "\n*Сигнал на вход в ЛОНГ:*\n"
        msg += f"Рекомендуется вход от {price:.4f} USDT\n"
        msg += f"Цель (TP): {tp:.4f} USDT, Стоп-лосс (SL): {sl:.4f} USDT\n"
        msg += "Обратите внимание на подтверждающие сигналы объёмов и тренда."
        return msg

    elif short_conditions:
        tp = price - 1.5 * atr
        sl = price + 1 * atr
        msg += "\n*Сигнал на вход в ШОРТ:*\n"
        msg += f"Рекомендуется вход от {price:.4f} USDT\n"
        msg += f"Цель (TP): {tp:.4f} USDT, Стоп-лосс (SL): {sl:.4f} USDT\n"
        msg += "Обратите внимание на подтверждающие сигналы объёмов и тренда."
        return msg

    msg += "\nПока чётких сигналов на вход нет. Рекомендуется наблюдать за динамикой индикаторов и объёмов."
    return msg

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram: {e}")

def check_signals():
    signals = []
    for symbol in symbols:
        signal = get_signal(symbol)
        if signal:
            signals.append(signal)
    return signals

def send_status_update():
    status = "Бот работает. Текущие цены:\n"
    for symbol in symbols:
        klines = get_kline(symbol)
        if klines:
            last_price = klines[-1]["close"]
            status += f"{symbol.replace('-USDT','')}: {last_price}\n"
    send_telegram_message(status)

def start_bot():
    global bot_started
    if not bot_started:
        bot_started = True

        # При старте сразу анализируем сигналы
        signals = check_signals()
        if signals:
            for msg in signals:
                send_telegram_message(msg)
        else:
            send_telegram_message("⚪ Нет сигналов на вход в лонг или шорт при старте бота.")

        # Запускаем циклы для обновления сигналов и статуса
        def signals_loop():
            while True:
                time.sleep(5 * 60)  # каждые 5 минут
                signals = check_signals()
                if signals:
                    for msg in signals:
                        send_telegram_message(msg)

        def status_loop():
            while True:
                time.sleep(30 * 60)  # каждые 30 минут
                send_status_update()

        threading.Thread(target=signals_loop, daemon=True).start()
        threading.Thread(target=status_loop, daemon=True).start()

@app.route("/")
def home():
    return "Bot is running!", 200

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
