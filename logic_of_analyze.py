import hmac
import hashlib
import requests
import pandas as pd
import pandas_ta as ta
from urllib.parse import urlencode
from datetime import datetime

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

def calculate_bollinger_bands(df, length=20, std_dev=2):
    bb_middle = ta.sma(df["close"], length)
    bb_std = ta.stdev(df["close"], length)
    upper = bb_middle + std_dev * bb_std
    lower = bb_middle - std_dev * bb_std
    return upper, lower

def detect_candle_pattern(df):
    if len(df) < 2:
        return ""

    last = df.iloc[-1]
    prev = df.iloc[-2]

    body_last = abs(last["close"] - last["open"])
    body_prev = abs(prev["close"] - prev["open"])

    # Бычье поглощение
    if (last["close"] > last["open"] and prev["close"] < prev["open"] and
        last["close"] > prev["open"] and last["open"] < prev["close"]):
        return "Паттерн: бычье поглощение"

    # Медвежье поглощение
    if (last["close"] < last["open"] and prev["close"] > prev["open"] and
        last["open"] > prev["close"] and last["close"] < prev["open"]):
        return "Паттерн: медвежье поглощение"

    # Молот
    if body_last < (last["high"] - last["low"]) * 0.3 and (last["close"] - last["low"]) < body_last * 0.2:
        return "Паттерн: молот"

    # Доджи
    if body_last < (last["high"] - last["low"]) * 0.1:
        return "Паттерн: доджи"

    return ""

def calculate_indicators(df):
    if df.empty or len(df) < 35:
        return None

    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["open"] = pd.to_numeric(df["open"], errors="coerce")
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    df["RSI_14"] = ta.rsi(df["close"], length=14)
    df["WR_14"] = ta.willr(df["high"], df["low"], df["close"], length=14)
    df["ATR_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["EMA_21"] = ta.ema(df["close"], length=21)

    upper_bb, lower_bb = calculate_bollinger_bands(df, length=20, std_dev=2)
    df["BB_upper"] = upper_bb
    df["BB_lower"] = lower_bb

    latest = df.iloc[-1]

    macd_val = latest["MACD_12_26_9"]
    signal_val = latest["MACDs_12_26_9"]
    rsi = latest["RSI_14"]
    wr = latest["WR_14"]
    atr = latest["ATR_14"]
    ema21 = latest["EMA_21"]
    price = latest["close"]
    volume_now = latest["volume"]
    volume_prev = df["volume"].iloc[-2]
    upper_band = latest["BB_upper"]
    lower_band = latest["BB_lower"]

    trend = "восходящий" if price > ema21 else "нисходящий"
    volume_trend = "растут" if volume_now > volume_prev else "падают"

    candle_pattern = detect_candle_pattern(df)

    signal = "Ожидание"
    if wr < -80 and macd_val > signal_val and 40 < rsi < 60 and trend == "восходящий" and volume_trend == "растут":
        if price > upper_band:
            signal = "Лонг"
    elif wr > -20 and macd_val < signal_val and rsi > 50 and trend == "нисходящий" and volume_trend == "падают":
        if price < lower_band:
            signal = "Шорт"

    return {
        "price": price,
        "ema21": ema21,
        "trend": trend,
        "macd": macd_val,
        "signal_line": signal_val,
        "rsi": rsi,
        "wr": wr,
        "atr": atr,
        "volume_now": volume_now,
        "volume_prev": volume_prev,
        "volume_trend": volume_trend,
        "candle_pattern": candle_pattern,
        "signal": signal,
        "bb_upper": upper_band,
        "bb_lower": lower_band
    }

def calculate_stop_take(price, atr, signal):
    multiplier_sl = 1.5
    multiplier_tp = 3.0

    if signal == "Лонг":
        stop_loss = price - atr * multiplier_sl
        take_profit = price + atr * multiplier_tp
    elif signal == "Шорт":
        stop_loss = price + atr * multiplier_sl
        take_profit = price - atr * multiplier_tp
    else:
        stop_loss = None
        take_profit = None

    return stop_loss, take_profit

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
        "1m": "ТФ 1m",
        "5m": "ТФ 5m",
        "15m": "ТФ 15m",
        "1h": "ТФ 1h"
    }

    for symbol in symbols:
        message = f"📊 Сигналы по монете <b>{symbol}</b> ({datetime.utcnow().strftime('%H:%M:%S UTC')}):\n\n"
        has_data = False

        for interval, label in intervals.items():
            klines = get_kline(symbol, interval, 100, api_secret, headers, base_url)
            if not klines:
                continue

            df = pd.DataFrame(klines)
            indicators = calculate_indicators(df)
            if not indicators:
                continue

            stop_loss, take_profit = calculate_stop_take(indicators["price"], indicators["atr"], indicators["signal"])

            tf_message = (
                f"{label}:\n"
                f"Цена: {indicators['price']:.4f} USDT | EMA(21): {indicators['ema21']:.4f} — тренд {indicators['trend']}\n"
                f"MACD: {indicators['macd']:.4f} vs сигнальная {indicators['signal_line']:.4f} — "
                f"{'бычий' if indicators['macd'] > indicators['signal_line'] else 'медвежий'}\n"
                f"RSI: {indicators['rsi']:.2f} ({'норма' if 30 < indicators['rsi'] < 70 else '⚠️'})\n"
                f"WR: {indicators['wr']:.2f} ({'перепродан' if indicators['wr'] < -80 else 'перекуплен' if indicators['wr'] > -20 else 'норма'})\n"
                f"Объём: {indicators['volume_now']:.1f} (до этого {indicators['volume_prev']:.1f}, {indicators['volume_trend']})\n"
                f"{indicators['candle_pattern']}\n"
                f"Рекомендация: <b>{indicators['signal']}</b>\n"
            )
            if stop_loss and take_profit:
                tf_message += f"Стоп-лосс: {stop_loss:.4f} | Тейк-профит: {take_profit:.4f}\n"
            message += tf_message + "\n"
            has_data = True

        if has_data:
            send_telegram_message(message, telegram_token, telegram_chat_id)
