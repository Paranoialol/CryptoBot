import time
import hmac
import hashlib
import requests
import pandas as pd
import numpy as np

# Таймфреймы для анализа
TIMEFRAMES = ["1m", "5m", "15m", "1h"]

# Функция подписи запроса
def sign_request(params, secret):
    query_string = "&".join([f"{key}={params[key]}" for key in sorted(params)])
    signature = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    return signature

# Получение данных свечей
def get_candles(symbol, interval, limit, api_secret, headers, base_url):
    path = "/market/kline"
    url = base_url + path
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "timestamp": int(time.time() * 1000)
    }
    params["sign"] = sign_request(params, api_secret)
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("success") != True or "data" not in data:
            return None
        df = pd.DataFrame(data["data"])
        df = df.rename(columns={
            "open": "open",
            "close": "close",
            "high": "high",
            "low": "low",
            "volume": "volume",
            "timestamp": "time"
        })
        df["time"] = pd.to_datetime(df["time"], unit='ms')
        df = df.astype({
            "open": float,
            "close": float,
            "high": float,
            "low": float,
            "volume": float,
        })
        return df
    except Exception:
        return None

# Индикаторы

def EMA(series, period):
    return series.ewm(span=period, adjust=False).mean()

def RSI(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def MACD(series, fast=12, slow=26, signal=9):
    ema_fast = EMA(series, fast)
    ema_slow = EMA(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = EMA(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def ATR(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

# Свечные паттерны

def is_bullish_engulfing(df):
    return (
        df["close"].iloc[-1] > df["open"].iloc[-1] and
        df["close"].iloc[-2] < df["open"].iloc[-2] and
        df["open"].iloc[-1] < df["close"].iloc[-2] and
        df["close"].iloc[-1] > df["open"].iloc[-2]
    )

def is_bearish_engulfing(df):
    return (
        df["close"].iloc[-1] < df["open"].iloc[-1] and
        df["close"].iloc[-2] > df["open"].iloc[-2] and
        df["open"].iloc[-1] > df["close"].iloc[-2] and
        df["close"].iloc[-1] < df["open"].iloc[-2]
    )

def is_hammer(df):
    body = abs(df["close"].iloc[-1] - df["open"].iloc[-1])
    lower_shadow = min(df["close"].iloc[-1], df["open"].iloc[-1]) - df["low"].iloc[-1]
    upper_shadow = df["high"].iloc[-1] - max(df["close"].iloc[-1], df["open"].iloc[-1])
    return lower_shadow > 2 * body and upper_shadow < body

def is_doji(df, tolerance=0.001):
    return abs(df["close"].iloc[-1] - df["open"].iloc[-1]) <= df["open"].iloc[-1] * tolerance

# Функция анализа символа

def analyze_symbol(symbol, api_secret, headers, base_url):
    result = {}
    for tf in TIMEFRAMES:
        df = get_candles(symbol, tf, 50, api_secret, headers, base_url)
        if df is None or df.empty:
            result[tf] = None
            continue

        df["EMA20"] = EMA(df["close"], 20)
        df["RSI14"] = RSI(df["close"], 14)
        df["MACD_line"], df["Signal_line"], df["MACD_hist"] = MACD(df["close"])
        df["ATR14"] = ATR(df)

        bullish = is_bullish_engulfing(df)
        bearish = is_bearish_engulfing(df)
        hammer = is_hammer(df)
        doji = is_doji(df)

        rsi = df["RSI14"].iloc[-1]
        rsi_overbought = rsi > 70
        rsi_oversold = rsi < 30

        macd_cross_up = df["MACD_line"].iloc[-2] < df["Signal_line"].iloc[-2] and df["MACD_line"].iloc[-1] > df["Signal_line"].iloc[-1]
        macd_cross_down = df["MACD_line"].iloc[-2] > df["Signal_line"].iloc[-2] and df["MACD_line"].iloc[-1] < df["Signal_line"].iloc[-1]

        ema_trend_up = df["close"].iloc[-1] > df["EMA20"].iloc[-1]
        ema_trend_down = df["close"].iloc[-1] < df["EMA20"].iloc[-1]

        signal = "Ожидание"
        if macd_cross_up and ema_trend_up and not rsi_overbought:
            if bullish:
                signal = "Сильный Лонг 📈 (Бычье поглощение)"
            elif hammer:
                signal = "Лонг 📈 (Молот)"
            elif doji:
                signal = "Лонг (Доджи — неопределенность)"
            else:
                signal = "Лонг 📈 (по индикаторам)"
        elif macd_cross_down and ema_trend_down and not rsi_oversold:
            if bearish:
                signal = "Сильный Шорт 📉 (Медвежье поглощение)"
            elif hammer:
                signal = "Шорт 📉 (Молот, осторожно)"
            elif doji:
                signal = "Шорт (Доджи — неопределенность)"
            else:
                signal = "Шорт 📉 (по индикаторам)"

        explanation = (
            f"RSI: {rsi:.2f} {'(перекуплен)' if rsi_overbought else '(перепродан)' if rsi_oversold else '(норма)'}\n"
            f"MACD гистограмма: {df['MACD_hist'].iloc[-1]:.5f}\n"
            f"EMA20: {df['EMA20'].iloc[-1]:.5f}\n"
            f"Свеча: Open {df['open'].iloc[-1]:.5f}, Close {df['close'].iloc[-1]:.5f}\n"
            f"Паттерны: " + ("Бычье поглощение, " if bullish else "") + ("Медвежье поглощение, " if bearish else "") + ("Молот, " if hammer else "") + ("Доджи, " if doji else "")).rstrip(", ") + "\n"
        )

        result[tf] = {
            "signal": signal,
            "explanation": explanation
        }
    return result

# Главная функция анализа

def analyze(symbols, api_secret, headers, telegram_token, telegram_chat_id, base_url):
    all_results = {}
    for symbol in symbols:
        res = analyze_symbol(symbol, api_secret, headers, base_url)
        all_results[symbol] = res

    message_lines = []
    for symbol, tf_results in all_results.items():
        message_lines.append(f"\n📊 Анализ {symbol}:")
        for tf, data in tf_results.items():
            if data is None:
                message_lines.append(f"{tf}: ❌ Нет данных")
            else:
                message_lines.append(f"{tf}: {data['signal']}\n{data['explanation']}")

    full_message = "\n".join(message_lines)
    send_telegram_message(full_message, telegram_token, telegram_chat_id)

# Функция отправки (используется только изнутри)
def send_telegram_message(message, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        requests.post(url, data=payload)
    except:
        pass
