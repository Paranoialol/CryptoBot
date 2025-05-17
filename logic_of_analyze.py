import os
import time
import hmac
import hashlib
import requests
import pandas as pd
import numpy as np

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
BASE_URL = "https://api.bingx.com/api/v3/futures"

# Таймфреймы для анализа
TIMEFRAMES = ["1m", "5m", "15m", "1h"]

# Функция подписи запроса
def sign_request(params, secret):
    query_string = "&".join([f"{key}={params[key]}" for key in sorted(params)])
    signature = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    return signature

# Получаем свечные данные фьючерсов
def get_candles(symbol, interval, limit=50):
    path = "/market/kline"
    url = BASE_URL + path
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "timestamp": int(time.time() * 1000)
    }
    params["sign"] = sign_request(params, API_SECRET)
    headers = {
        "X-BX-APIKEY": API_KEY
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data["success"] != True or "data" not in data:
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
        # В BingX timestamp может идти в мс
        df["time"] = pd.to_datetime(df["time"], unit='ms')
        df = df.astype({
            "open": float,
            "close": float,
            "high": float,
            "low": float,
            "volume": float,
        })
        return df
    except Exception as e:
        # Отправка лога в телеграм должна быть в основном файле, здесь просто возвращаем None
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

# Свечные паттерны с пояснениями

def is_bullish_engulfing(df):
    # Текущая свеча — бычья и тело полностью поглощает тело предыдущей медвежьей свечи
    cond1 = (df["close"].iloc[-1] > df["open"].iloc[-1])
    cond2 = (df["close"].iloc[-2] < df["open"].iloc[-2])
    cond3 = (df["open"].iloc[-1] < df["close"].iloc[-2])
    cond4 = (df["close"].iloc[-1] > df["open"].iloc[-2])
    return cond1 and cond2 and cond3 and cond4

def is_bearish_engulfing(df):
    # Текущая свеча — медвежья и тело полностью поглощает тело предыдущей бычьей свечи
    cond1 = (df["close"].iloc[-1] < df["open"].iloc[-1])
    cond2 = (df["close"].iloc[-2] > df["open"].iloc[-2])
    cond3 = (df["open"].iloc[-1] > df["close"].iloc[-2])
    cond4 = (df["close"].iloc[-1] < df["open"].iloc[-2])
    return cond1 and cond2 and cond3 and cond4

def is_hammer(df):
    body = abs(df["close"].iloc[-1] - df["open"].iloc[-1])
    lower_shadow = df["open"].iloc[-1] - df["low"].iloc[-1] if df["open"].iloc[-1] > df["close"].iloc[-1] else df["close"].iloc[-1] - df["low"].iloc[-1]
    upper_shadow = df["high"].iloc[-1] - max(df["open"].iloc[-1], df["close"].iloc[-1])
    return (lower_shadow > 2 * body) and (upper_shadow < body)

def is_doji(df, tolerance=0.001):
    return abs(df["close"].iloc[-1] - df["open"].iloc[-1]) <= (df["open"].iloc[-1] * tolerance)

# Основной анализ по символу и таймфрейму

def analyze_symbol(symbol):
    results = {}
    for tf in TIMEFRAMES:
        df = get_candles(symbol, tf, limit=50)
        if df is None or df.empty:
            results[tf] = None
            continue

        # Вычисляем индикаторы
        df["EMA20"] = EMA(df["close"], 20)
        df["RSI14"] = RSI(df["close"], 14)
        macd_line, signal_line, hist = MACD(df["close"])
        df["MACD_line"] = macd_line
        df["Signal_line"] = signal_line
        df["MACD_hist"] = hist
        df["ATR14"] = ATR(df)

        # Определяем паттерны
        bullish_engulfing = is_bullish_engulfing(df)
        bearish_engulfing = is_bearish_engulfing(df)
        hammer = is_hammer(df)
        doji = is_doji(df)

        # Логика сигналов — комплексная, с пояснениями
        signal = "Ожидание"

        # MACD - кроссовер для входа
        macd_cross_up = (df["MACD_line"].iloc[-2] < df["Signal_line"].iloc[-2]) and (df["MACD_line"].iloc[-1] > df["Signal_line"].iloc[-1])
        macd_cross_down = (df["MACD_line"].iloc[-2] > df["Signal_line"].iloc[-2]) and (df["MACD_line"].iloc[-1] < df["Signal_line"].iloc[-1])

        # RSI уровни
        rsi = df["RSI14"].iloc[-1]
        rsi_overbought = rsi > 70
        rsi_oversold = rsi < 30

        # EMA тренд
        ema_trend_up = df["close"].iloc[-1] > df["EMA20"].iloc[-1]
        ema_trend_down = df["close"].iloc[-1] < df["EMA20"].iloc[-1]

        # Логика сигналов с учетом паттернов и индикаторов
        if macd_cross_up and ema_trend_up and not rsi_overbought:
            if bullish_engulfing:
                signal = "Сильный Лонг 📈 (Бычье поглощение)"
            elif hammer:
                signal = "Лонг 📈 (Паттерн Молот)"
            elif doji:
                signal = "Лонг с осторожностью (Доджи - неопределенность)"
            else:
                signal = "Лонг 📈 (MACD и EMA подтверждают)"
        elif macd_cross_down and ema_trend_down and not rsi_oversold:
            if bearish_engulfing:
                signal = "Сильный Шорт 📉 (Медвежье поглощение)"
            elif hammer:
                signal = "Шорт 📉 (Паттерн Молот, но осторожно)"
            elif doji:
                signal = "Шорт с осторожностью (Доджи - неопределенность)"
            else:
                signal = "Шорт 📉 (MACD и EMA подтверждают)"
        else:
            signal = "Ожидание (Нет четкого сигнала)"

        # Формируем пояснение по индикаторам
        explanation = (
            f"RSI: {rsi:.2f} {'(перекуплен)' if rsi_overbought else '(перепродан)' if rsi_oversold else '(норма)'}\n"
            f"MACD гистограмма: {df['MACD_hist'].iloc[-1]:.5f}\n"
            f"EMA20: {df['EMA20'].iloc[-1]:.5f}\n"
            f"Последняя свеча: Open {df['open'].iloc[-1]:.5f}, Close {df['close'].iloc[-1]:.5f}\n"
            f"Паттерны: "
            + (("Бычье поглощение, " if bullish_engulfing else "") +
               ("Медвежье поглощение, " if bearish_engulfing else "") +
               ("Молот, " if hammer else "") +
               ("Доджи, " if doji else "")).rstrip(", ") +
            "\n"
        )

        results[tf] = {
            "signal": signal,
            "explanation": explanation,
            "data": df.tail(3).to_dict(orient="records")  # последние 3 свечи для контекста
        }
    return results


def analyze(symbols):
    all_results = {}
    for symbol in symbols:
        res = analyze_symbol(symbol)
        all_results[symbol] = res

    # Формируем сообщение для отправки
    messages = []
    for symbol, res in all_results.items():
        messages.append(f"📊 Анализ для {symbol}:\n")
        for tf, data in res.items():
            if data is None:
                messages.append(f"{tf}: ❌ Нет данных\n")
            else:
                messages.append(f"{tf}: {data['signal']}\n{data['explanation']}")
    full_message = "\n".join(messages)

    # Отправка сообщения через функцию из основного файла (твой код)
    send_telegram_message(full_message)


# Заглушка для функции отправки, в твоем коде она есть, поэтому здесь не трогаем
def send_telegram_message(text):
    # В основном файле у тебя своя реализация
    pass

