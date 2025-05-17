# File: logic_of_analyze.py
import os
import time
import hmac
import hashlib
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from your_telegram_module import send_telegram

API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
BASE_URL = "https://api.bingx.com/api/v3/futures"
HEADERS = {
    'Content-Type': 'application/json',
    'X-API-KEY': API_KEY,
}

def log_debug(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    send_telegram(f"My CryptoFTW bot:\n🐞 DEBUG [{timestamp}]:\n{msg}")

def sign_request(params: dict, secret: str):
    query_string = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def get_klines(symbol: str, interval: str, limit=100):
    path = "/market/kline"
    url = BASE_URL + path
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    params['signature'] = sign_request(params, API_SECRET)
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'data' in data and data['data']:
            df = pd.DataFrame(data['data'])
            for col in ['open', 'close', 'high', 'low', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df.sort_values('time')
        log_debug(f"Нет данных или пустой ответ для {symbol} {interval}: {data}")
    except Exception as e:
        log_debug(f"Ошибка при получении данных {symbol} {interval}: {e}")
    return pd.DataFrame()

# Индикаторы технического анализа
def EMA(series, period):
    return series.ewm(span=period, adjust=False).mean()

def MACD(df):
    ema12 = EMA(df['close'], 12)
    ema26 = EMA(df['close'], 26)
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    return macd_line, signal, hist

def RSI(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)  # если NaN — считаем нейтральным

def ATR(df, period=14):
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# Свечные паттерны — с пояснениями
def bullish_engulfing(df):
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    cond = (
        prev['close'] < prev['open'] and
        curr['close'] > curr['open'] and
        curr['open'] < prev['close'] and
        curr['close'] > prev['open']
    )
    return cond

def bearish_engulfing(df):
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    cond = (
        prev['close'] > prev['open'] and
        curr['close'] < curr['open'] and
        curr['open'] > prev['close'] and
        curr['close'] < prev['open']
    )
    return cond

def hammer(df):
    if len(df) < 1:
        return False
    candle = df.iloc[-1]
    body = abs(candle['close'] - candle['open'])
    lower_shadow = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
    upper_shadow = candle['high'] - max(candle['close'], candle['open'])
    cond = lower_shadow > 2 * body and upper_shadow < body * 0.3
    return cond

def inverted_hammer(df):
    if len(df) < 1:
        return False
    candle = df.iloc[-1]
    body = abs(candle['close'] - candle['open'])
    upper_shadow = candle['high'] - max(candle['close'], candle['open'])
    lower_shadow = min(candle['close'], candle['open']) - candle['low']
    cond = upper_shadow > 2 * body and lower_shadow < body * 0.3
    return cond

def doji(df, threshold=0.1):
    if len(df) < 1:
        return False
    candle = df.iloc[-1]
    body = abs(candle['close'] - candle['open'])
    candle_range = candle['high'] - candle['low']
    cond = body <= candle_range * threshold
    return cond

def evening_star(df):
    # Классический паттерн "Вечерняя звезда" из 3 свечей (медвежий разворот)
    if len(df) < 3:
        return False
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    cond1 = c1['close'] > c1['open']  # первая свеча — бычья
    cond2 = abs(c2['close'] - c2['open']) < (c2['high'] - c2['low']) * 0.3  # вторая — доджи или маленькое тело
    cond3 = c3['close'] < c3['open'] and c3['close'] < (c1['close'] + c1['open']) / 2  # третья — сильная медвежья свеча закрытия ниже середины первой
    return cond1 and cond2 and cond3

def morning_star(df):
    # Классический паттерн "Утренняя звезда" из 3 свечей (бычий разворот)
    if len(df) < 3:
        return False
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    cond1 = c1['close'] < c1['open']  # первая свеча — медвежья
    cond2 = abs(c2['close'] - c2['open']) < (c2['high'] - c2['low']) * 0.3  # вторая — доджи или маленькое тело
    cond3 = c3['close'] > c3['open'] and c3['close'] > (c1['close'] + c1['open']) / 2  # третья — сильная бычья свеча закрытия выше середины первой
    return cond1 and cond2 and cond3

# Основная функция анализа
def analyze_symbol(symbol: str):
    intervals = ['1m', '5m', '15m', '1h']
    results = {}

    for interval in intervals:
        df = get_klines(symbol, interval)
        if df.empty or len(df) < 30:
            results[interval] = {"signal": None, "explanation": "Недостаточно данных для анализа."}
            continue

        macd_line, signal_line, hist = MACD(df)
        rsi = RSI(df['close'])
        atr = ATR(df)

        last_macd = macd_line.iloc[-1]
        last_signal = signal_line.iloc[-1]
        last_rsi = rsi.iloc[-1]
        last_close = df['close'].iloc[-1]
        last_atr = atr.iloc[-1]
        volume = df['volume'].iloc[-1]

        # Проверяем свечные паттерны
        patterns_found = []
        pattern_messages = []
        if bullish_engulfing(df):
            patterns_found.append("Бычье поглощение (Bullish Engulfing)")
            pattern_messages.append("💚 Бычье поглощение — сильный сигнал возможного разворота вверх.")
        if bearish_engulfing(df):
            patterns_found.append("Медвежье поглощение (Bearish Engulfing)")
            pattern_messages.append("🔴 Медвежье поглощение — сигнал возможного разворота вниз.")
        if hammer(df):
            patterns_found.append("Молот (Hammer)")
            pattern_messages.append("🔹 Молот — потенциальный разворот вверх после падения.")
        if inverted_hammer(df):
            patterns_found.append("Перевёрнутый молот (Inverted Hammer)")
            pattern_messages.append("🔸 Перевёрнутый молот — предупреждение о развороте вверх.")
        if doji(df):
            patterns_found.append("Доджи (Doji)")
            pattern_messages.append("⚪ Доджи — неуверенность рынка, возможен разворот.")
        if evening_star(df):
            patterns_found.append("Вечерняя звезда (Evening Star)")
            pattern_messages.append("🌒 Вечерняя звезда — сильный медвежий паттерн, возможен разворот вниз.")
        if morning_star(df):
            patterns_found.append("Утренняя звезда (Morning Star)")
            pattern_messages.append("🌕 Утренняя звезда — сильный бычий паттерн, возможен разворот вверх.")
        # Логика определения сигнала
        reasons = []
        signal = "Ожидание"

        # MACD пересечение
        if last_macd > last_signal:
            reasons.append("MACD показывает бычий настрой (гистограмма выше сигнальной линии).")
        else:
            reasons.append("MACD показывает медвежий настрой (гистограмма ниже сигнальной линии).")

        # RSI — перекупленность/перепроданность
        if last_rsi > 70:
            reasons.append("RSI выше 70 — рынок перекуплен, возможен откат вниз.")
        elif last_rsi < 30:
            reasons.append("RSI ниже 30 — рынок перепродан, возможен разворот вверх.")
        else:
            reasons.append(f"RSI в зоне {round(last_rsi,1)} — нейтральный тренд.")

        # Свечные паттерны
        if patterns_found:
            reasons.append("Обнаружены свечные паттерны:")
            reasons.extend(pattern_messages)

        # Объём — фильтр для силы сигнала
        if volume < 10:
            reasons.append("⚠️ Объём низкий, сигнал может быть слабым и ненадежным.")

        # Итоговая логика для сигнала
        bullish_conditions = (
            last_macd > last_signal and last_rsi < 60 and
            any(p in patterns_found for p in [
                "Бычье поглощение (Bullish Engulfing)",
                "Молот (Hammer)",
                "Утренняя звезда (Morning Star)"
            ])
        )
        bearish_conditions = (
            last_macd < last_signal and last_rsi > 40 and
            any(p in patterns_found for p in [
                "Медвежье поглощение (Bearish Engulfing)",
                "Вечерняя звезда (Evening Star)"
            ])
        )

        if bullish_conditions:
            signal = "Лонг"
            reasons.append("📈 Рекомендуется входить в Лонг — сигналы сходятся.")
        elif bearish_conditions:
            signal = "Шорт"
            reasons.append("📉 Рекомендуется входить в Шорт — сигналы сходятся.")
        else:
            reasons.append("⏳ Сигналы смешанные, рекомендуется подождать подтверждения.")

        stop_loss = last_close - 1.5 * last_atr if signal == "Лонг" else last_close + 1.5 * last_atr
        take_profit = last_close + 3 * last_atr if signal == "Лонг" else last_close - 3 * last_atr

        explanation = "\n".join(reasons)

        results[interval] = {
            "signal": signal,
            "close": round(last_close, 6),
            "rsi": round(last_rsi, 2),
            "macd_hist": round(hist.iloc[-1], 6),
            "stop_loss": round(stop_loss, 6),
            "take_profit": round(take_profit, 6),
            "volume": round(volume, 2),
            "explanation": explanation
        }

    return results # Эта строка должна быть здесь, вне цикла for interval

def analyze(symbols):
    messages = []
    for symbol in symbols:
        analysis = analyze_symbol(symbol)
        msg = f"🚀 Анализ по {symbol} 🚀\n\n"
        for interval, res in analysis.items():
            if res["signal"] is None:
                msg += f"⏳ {interval}: недостаточно данных для анализа.\n\n"
            else:
                # Эмоциональный, человечный стиль с эмодзи и ясными пояснениями
                msg += (
                    f"⏰ {interval}\n"
                    f"Сигнал: {res['signal']}\n"
                    f"Цена закрытия: {res['close']}\n"
                    f"RSI: {res['rsi']} | MACD гистограмма: {res['macd_hist']}\n"
                    f"Объём: {res['volume']}\n"
                    f"🛑 Стоп-лосс: {res['stop_loss']} | 🎯 Тейк-профит: {res['take_profit']}\n"
                    f"🔍 Пояснение:\n{res['explanation']}\n\n"
                )
        messages.append(msg)
        log_debug(msg) # Эта строка должна быть здесь, внутри цикла for symbol, после формирования полного сообщения для символа
    return messages
