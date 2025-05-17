import time
import hmac
import hashlib
import requests
import pandas as pd
import numpy as np

TIMEFRAMES = ["1m", "5m", "15m", "1h"]

def sign_request(params, secret):
    query_string = "&".join([f"{key}={params[key]}" for key in sorted(params)])
    signature = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    return signature

def get_candles(symbol, interval, limit, api_secret, headers, base_url):
    path = "/openApi/market/kline"
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
        data = response.json()
        if not data.get("success") or "data" not in data:
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
            "volume": float
        })
        return df
    except:
        return None

def EMA(series, period):
    return series.ewm(span=period, adjust=False).mean()

def RSI(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def MACD(series, fast=12, slow=26, signal=9):
    ema_fast = EMA(series, fast)
    ema_slow = EMA(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = EMA(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def analyze(symbols, api_secret, headers, telegram_token, telegram_chat_id, base_url):
    message_lines = []

    for symbol in symbols:
        message_lines.append(f"\n📊 Анализ {symbol}:")
        for tf in TIMEFRAMES:
            df = get_candles(symbol, tf, 100, api_secret, headers, base_url)
            if df is None or df.empty:
                message_lines.append(f"{tf}: ❌ Нет данных")
                continue

            try:
                rsi = RSI(df["close"]).iloc[-1]
                macd_line, signal_line, hist = MACD(df["close"])
                last_hist = hist.iloc[-1]

                trend = "Ожидание"
                if last_hist > 0 and rsi < 70:
                    trend = "Лонг 📈"
                elif last_hist < 0 and rsi > 30:
                    trend = "Шорт 📉"

                message_lines.append(f"{tf}: {trend} | RSI: {rsi:.2f}, MACD_hist: {last_hist:.4f}")
            except:
                message_lines.append(f"{tf}: ⚠️ Ошибка при анализе")

    full_message = "\n".join(message_lines)
    send_telegram_message(full_message, telegram_token, telegram_chat_id)

def send_telegram_message(message, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        requests.post(url, data=payload)
    except:
        pass
