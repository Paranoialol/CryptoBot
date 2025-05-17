# File: logic_of_analyze.py
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

def calculate_indicators_v2(df):
    if df.empty or len(df) < 35:
        return None

    # Приведение данных к числам
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["open"] = pd.to_numeric(df["open"], errors="coerce")
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    # Индикаторы
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    df["RSI_14"] = ta.rsi(df["close"], length=14)
    df["WR_14"] = ta.willr(df["high"], df["low"], df["close"], length=14)
    df["ATR_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["EMA_21"] = ta.ema(df["close"], length=21)
    df["ADX_14"] = ta.adx(df["high"], df["low"], df["close"], length=14)["ADX_14"]

    # SuperTrend (pandas_ta)
    st = ta.supertrend(df["high"], df["low"], df["close"], length=10, multiplier=3.0)
    df = pd.concat([df, st], axis=1)  # добавятся столбцы SUPERT_10_3.0 и SUPERTd_10_3.0

    latest = df.iloc[-1]

    macd_val = latest["MACD_12_26_9"]
    signal_val = latest["MACDs_12_26_9"]
    rsi = latest["RSI_14"]
    wr = latest["WR_14"]
    atr = latest["ATR_14"]
    ema21 = latest["EMA_21"]
    adx = latest["ADX_14"]
    supertrend_dir = latest["SUPERTd_10_3.0"]  # 1 - вверх, -1 - вниз, 0 - без тренда

    price = latest["close"]
    volume_now = latest["volume"]
    volume_prev = df["volume"].iloc[-2]
    volume_trend = "растут" if volume_now > volume_prev else "падают"

    # Оценка по индикаторам (баллы)
    score = 0

    # MACD
    if macd_val > signal_val:
        score += 2
    else:
        score -= 2

    # RSI
    if rsi < 30:
        score += 1
    elif rsi > 70:
        score -= 1

    # Williams %R
    if wr < -80:
        score += 1
    elif wr > -20:
        score -= 1

    # EMA21
    if price > ema21:
        score += 2
    else:
        score -= 2

    # ADX
    if adx > 25:
        score += 1
    else:
        score -= 1

    # SuperTrend
    if supertrend_dir == 1:
        score += 2
    elif supertrend_dir == -1:
        score -= 2

    # Фильтры по объему и волатильности
    volume_filter = volume_now > volume_prev * 0.8
    atr_filter = atr < price * 0.05

    candle_pattern = detect_candle_pattern(df)

    signal = "Лонг" if score > 3 else "Шорт" if score < -3 else "Ожидание"

    return {
        "price": price,
        "score": score,
        "volume_filter": volume_filter,
        "atr_filter": atr_filter,
        "signal": signal,
        "volume_now": volume_now,
        "volume_prev": volume_prev,
        "atr": atr,
        "ema21": ema21,
        "adx": adx,
        "supertrend_dir": supertrend_dir,
        "candle_pattern": candle_pattern
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
        "1m": 0.5,
        "5m": 1.0,
        "15m": 1.5,
        "1h": 2.0
    }

    for symbol in symbols:
        message = f"📊 Сигналы по монете <b>{symbol}</b> ({datetime.utcnow().strftime('%H:%M:%S UTC')}):\n\n"
        combined_score = 0
        valid_intervals = 0

        for interval, weight in intervals.items():
            klines = get_kline(symbol, interval, 100, api_secret, headers, base_url)
            if not klines:
                continue

            df = pd.DataFrame(klines)
            indicators = calculate_indicators_v2(df)
            if not indicators:
                continue

            # Проверяем фильтры по объему и волатильности
            if not indicators["volume_filter"] or not indicators["atr_filter"]:
                color = "🔴"
                tf_signal = "Сигнал отсеян (фильтры)"
            else:
                # Светофор по баллам
                if indicators["score"] >= 5:
                    color = "🟢"
                elif 2 <= indicators["score"] < 5:
                    color = "🟡"
                else:
                    color = "🔴"
                tf_signal = indicators["signal"]
                combined_score += indicators["score"] * weight
                valid_intervals += weight

            stop_loss, take_profit = calculate_stop_take(indicators["price"], indicators["atr"], indicators["signal"])

            message += (
                f"{interval} {color}:\n"
                f"Сигнал: <b>{tf_signal}</b> | Балл: {indicators['score']:.1f}\n"
                f"Цена: {indicators['price']:.4f} | ATR : {indicators['atr']:.4f} | Объем: {indicators['volume_now']:.1f}\n"
                f"Паттерн: {indicators['candle_pattern']}\n"
                f"Стоп-лосс: {stop_loss:.4f} | Тейк-профит: {take_profit:.4f}\n\n"
            )

        if valid_intervals == 0:
            message += "❌ Нет достаточных данных для анализа.\n"
        else:
            avg_score = combined_score / valid_intervals
            if avg_score > 3:
                overall = "🟢 Общий сигнал: Лонг"
            elif avg_score < -3:
                overall = "🔴 Общий сигнал: Шорт"
            else:
                overall = "🟡 Общий сигнал: Ожидание"
            message += f"<b>{overall}</b> (Средний балл: {avg_score:.2f})\n"

        send_telegram_message(message, telegram_token, telegram_chat_id)
