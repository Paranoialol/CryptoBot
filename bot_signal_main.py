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
from datetime import datetime

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
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        response_data = res.json()
        if 'data' in response_data and response_data['data']:
            return response_data['data']
    except Exception as e:
        send_telegram_message(f"Ошибка при получении свечей {symbol}: {e}")
    return []


def detect_reversal_patterns(df):
    # Упрощённые разворотные паттерны (бычье/медвежье поглощение)
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]

    bullish_engulfing = (
        last_candle['close'] > last_candle['open'] and
        prev_candle['close'] < prev_candle['open'] and
        last_candle['open'] < prev_candle['close'] and
        last_candle['close'] > prev_candle['open']
    )

    bearish_engulfing = (
        last_candle['close'] < last_candle['open'] and
        prev_candle['close'] > prev_candle['open'] and
        last_candle['open'] > prev_candle['close'] and
        last_candle['close'] < prev_candle['open']
    )

    if bullish_engulfing:
        return "🔼 Бычье поглощение"
    elif bearish_engulfing:
        return "🔽 Медвежье поглощение"
    return ""


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

        pattern = detect_reversal_patterns(df)

        return {
            "macd": macd.iloc[-1],
            "rsi": rsi.iloc[-1],
            "wr": wr.iloc[-1],
            "ema": ema.iloc[-1],
            "ema_prev": ema.iloc[-2] if len(ema) > 1 else ema.iloc[-1],
            "volume": df["volume"].iloc[-1],
            "volume_prev": df["volume"].iloc[-2],
            "atr": atr.iloc[-1],
            "price": df["close"].iloc[-1],
            "fibo_618": fibo_618,
            "fibo_5": fibo_5,
            "fibo_382": fibo_382,
            "pattern": pattern
        }
    except Exception as e:
        send_telegram_message(f"Ошибка в расчёте индикаторов: {e}")
        return None


def generate_signal_message(symbol, ind):
    price = ind["price"]
    ema = ind["ema"]
    macd_val = ind["macd"]["MACD_12_26_9"]
    macd_signal = ind["macd"]["MACDs_12_26_9"]
    rsi = ind["rsi"]
    wr = ind["wr"]
    atr = ind["atr"]
    vol, vol_prev = ind["volume"], ind["volume_prev"]

    trend = "восходящий" if price > ema else "нисходящий"
    volume_trend = "растут" if vol > vol_prev else "падают"
    macd_dir = "бычий" if macd_val > macd_signal else "медвежий"

    msg = f"🧾 Анализ монеты *{symbol.replace('-USDT','')}* ({datetime.utcnow().strftime('%H:%M:%S')} UTC)\n"
    msg += f"Цена: {price:.4f} USDT\n"
    msg += f"EMA(21): {ema:.4f} — тренд *{trend}*\n"
    msg += f"MACD: {macd_val:.4f} vs сигнальная {macd_signal:.4f} — *{macd_dir} сигнал*\n"
    msg += f"RSI: {rsi:.2f} — "
    msg += "*перепроданность*\n" if rsi < 30 else ("*перекупленность*\n" if rsi > 70 else "в норме\n")
    msg += f"WR: {wr:.2f} — "
    msg += "*перепродан*\n" if wr < -80 else ("*перекуп*\n" if wr > -20 else "в нейтральной зоне\n")
    msg += f"Объём: {vol} (до этого был {vol_prev}) — *объёмы {volume_trend}*\n"

    if ind["pattern"]:
        msg += f"Свечной паттерн: {ind['pattern']}\n"

    long_ok = macd_val > macd_signal and rsi < 50 and wr < -80 and vol > vol_prev and price > ema
    short_ok = macd_val < macd_signal and rsi > 60 and wr > -20 and vol > vol_prev and price < ema

    if long_ok:
        tp, sl = price + 1.5 * atr, price - 1.0 * atr
        msg += f"\n📈 *ЛОНГ сигнал!*\nВход от: {price:.4f}\nTP: {tp:.4f} | SL: {sl:.4f}"
    elif short_ok:
        tp, sl = price - 1.5 * atr, price + 1.0 * atr
        msg += f"\n📉 *ШОРТ сигнал!*\nВход от: {price:.4f}\nTP: {tp:.4f} | SL: {sl:.4f}"
    else:
        msg += f"\n⚪ Пока чётких сигналов нет. Я слежу дальше за ситуацией."

    return msg


def get_signal(symbol):
    klines = get_kline(symbol)
    if not klines or len(klines) < 50:
        return None
    ind = calculate_indicators(klines)
    if not ind:
        return None
    return generate_signal_message(symbol, ind)


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram: {e}")


def check_signals():
    signals = []
    for symbol in symbols:
        msg = get_signal(symbol)
        if msg:
            signals.append(msg)
    return signals


def send_status_update():
    status = "Бот работает. Текущие цены:\n"
    for symbol in symbols:
        klines = get_kline(symbol)
        if klines:
            try:
                last_price = float(klines[-1]["close"])
                status += f"{symbol.replace('-USDT','')}: {last_price}\n"
            except Exception:
                pass
    send_telegram_message(status)


def start_bot():
    global bot_started
    if not bot_started:
        bot_started = True

        signals = check_signals()
        if signals:
            for msg in signals:
                send_telegram_message(msg)
        else:
            send_telegram_message("⚪ Нет сигналов на вход при старте бота.")

        def signals_loop():
            while True:
                time.sleep(5 * 60)
                signals = check_signals()
                if signals:
                    for msg in signals:
                        send_telegram_message(msg)

        def status_loop():
            while True:
                time.sleep(30 * 60)
                send_status_update()

        threading.Thread(target=signals_loop, daemon=True).start()
        threading.Thread(target=status_loop, daemon=True).start()


@app.route("/")
def home():
    return "Bot is running!", 200


if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
