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

def log_debug(message, telegram_token, telegram_chat_id):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    full_message = f"🐞 <b>DEBUG [{timestamp}]</b>:\n{message}"
    send_telegram_message(full_message, telegram_token, telegram_chat_id)

def get_kline(symbol, interval, limit, api_secret, headers, base_url, telegram_token=None, telegram_chat_id=None):
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
            data = response.json().get("data", [])
            # Сортируем по времени, если есть поле openTime или timestamp
            if data:
                if isinstance(data[0], dict):
                    if "openTime" in data[0]:
                        data.sort(key=lambda x: x["openTime"])
                    elif "timestamp" in data[0]:
                        data.sort(key=lambda x: x["timestamp"])
            return data
        else:
            err_msg = f"Error fetching klines {symbol} {interval}: {response.status_code} - {response.text}"
            print(err_msg)
            if telegram_token and telegram_chat_id:
                log_debug(err_msg, telegram_token, telegram_chat_id)
    except Exception as e:
        err_msg = f"Exception fetching kline for {symbol} ({interval}): {e}"
        print(err_msg)
        if telegram_token and telegram_chat_id:
            log_debug(err_msg, telegram_token, telegram_chat_id)
    return []

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

    # Сортировка по времени
    if "openTime" in df.columns:
        df = df.sort_values("openTime")
    elif "timestamp" in df.columns:
        df = df.sort_values("timestamp")

    # Приведение к числовому типу
    for col in ["close", "open", "high", "low", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Удаляем NaN в критичных столбцах
    df = df.dropna(subset=["close", "open", "high", "low", "volume"])

    # Индикаторы
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    df["RSI_14"] = ta.rsi(df["close"], length=14)
    df["WR_14"] = ta.willr(df["high"], df["low"], df["close"], length=14)
    df["ATR_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["EMA_21"] = ta.ema(df["close"], length=21)
    df["ADX_14"] = ta.adx(df["high"], df["low"], df["close"], length=14)["ADX_14"]

    st = ta.supertrend(df["high"], df["low"], df["close"], length=10, multiplier=3.0)
    df = pd.concat([df, st], axis=1)

    latest = df.iloc[-1]

    macd_val = latest.get("MACD_12_26_9", 0)
    signal_val = latest.get("MACDs_12_26_9", 0)
    rsi = latest.get("RSI_14", 0)
    wr = latest.get("WR_14", 0)
    atr = latest.get("ATR_14", 0)
    ema21 = latest.get("EMA_21", 0)
    adx = latest.get("ADX_14", 0)
    supertrend_dir = latest.get("SUPERTd_10_3.0", 0)

    price = latest["close"]
    volume_now = latest["volume"]
    volume_prev = df["volume"].iloc[-2] if len(df) > 1 else volume_now
    volume_trend = "растут" if volume_now > volume_prev else "падают"

    score = 0
    if macd_val > signal_val:
        score += 2
    else:
        score -= 2

    if rsi < 30:
        score += 1
    elif rsi > 70:
        score -= 1

    if wr < -80:
        score += 1
    elif wr > -20:
        score -= 1

    if price > ema21:
        score += 2
    else:
        score -= 2

    if adx > 25:
        score += 1
    else:
        score -= 1

    if supertrend_dir == 1:
        score += 2
    elif supertrend_dir == -1:
        score -= 2

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
            klines = get_kline(symbol, interval, 100, api_secret, headers, base_url, telegram_token, telegram_chat_id)
            if not klines:
                log_debug(f"Нет данных для {symbol} {interval}", telegram_token, telegram_chat_id)
                continue

            df = pd.DataFrame(klines)

            # Логирование для отладки данных по таймфрейму
            log_debug(f"Данные {symbol} {interval} (первые 3 строки):\n{df.head(3).to_string()}", telegram_token, telegram_chat_id)

            # Проверяем наличие критичных столбцов
            required_cols = ["open", "close", "high", "low", "volume"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                log_debug(f"Отсутствуют столбцы в данных {symbol} {interval}: {missing_cols}", telegram_token, telegram_chat_id)
                continue

            # Приведение типов и сортировка
            if "openTime" in df.columns:
                df = df.sort_values("openTime")
            elif "timestamp" in df.columns:
                df = df.sort_values("timestamp")

            for col in required_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            indicators = calculate_indicators_v2(df)
            if not indicators:
                log_debug(f"Недостаточно данных для расчёта индикаторов {symbol} {interval}", telegram_token, telegram_chat_id)
                continue

            if not indicators["volume_filter"] or not indicators["atr_filter"]:
                color = "🔴"
                tf_signal = "Сигнал отсеян (фильтры)"
            else:
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
    if valid_intervals > 0:
        avg_score = combined_score / valid_intervals
        overall_signal = "Лонг" if avg_score > 3 else "Шорт" if avg_score < -3 else "Ожидание"
    else:
        overall_signal = "Нет данных"

    message += f"⚖️ Общий сигнал: <b>{overall_signal}</b>"

    send_telegram_message(message, telegram_token, telegram_chat_id)
 
