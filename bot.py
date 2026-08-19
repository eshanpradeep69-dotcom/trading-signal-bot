import requests
import time
from datetime import datetime, time as dtime
import pytz

# ====== SETTINGS ======
TELEGRAM_TOKEN = "8488480027:AAFyTg91j9bqgHcRfEvBD9BQh5VifGYdNBI"
TELEGRAM_CHAT_ID = "7973906409"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "TRXUSDT", "TONUSDT", "SHIBUSDT", "AVAXUSDT", "DOTUSDT",
    "LINKUSDT", "BCHUSDT", "NEARUSDT", "MATICUSDT", "APTUSDT", "ICPUSDT",
    "LTCUSDT", "ATOMUSDT", "STXUSDT", "FILUSDT", "HBARUSDT", "INJUSDT",
    "SUIUSDT", "TAOUSDT", "OPUSDT", "ARBUSDT", "PEPEUSDT", "WIFUSDT", # PEUSDT -> PEPEUSDT
  
]

POINTS_TP = 25
POINTS_SL = 20
CHECK_INTERVAL = 900 # 15min

TZ = pytz.timezone("Asia/Colombo")
sent_signals = set()
API_KEY = "5c254276ab884f34b2d9141f3e39d485" # <--- ඔයාගේ TwelveData Key

# ====== TELEGRAM ======
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, timeout=10)
    except:
        pass

# ====== DATA - TwelveData API ======
def fetch_ohlcv(symbol, interval, limit=100):
    url = f"https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval, # "15min" or "1h"
        "outputsize": limit,
        "apikey": API_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if 'values' not in data: return []
        candles = []
        for c in data['values']:
            candles.append({
                'time': c['datetime'],
                'open': float(c['open']),
                'high': float(c['high']),
                'low': float(c['low']),
                'close': float(c['close'])
            })
        return candles[::-1] # oldest first
    except Exception as e:
        print(f"API Error {symbol} {interval}: {e}")
        return []

# ====== NEW: ELLIOTT TREND FILTER 1H ======
def get_elliott_trend(candles_1h):
    if len(candles_1h) < 20: return "NONE"

    last20_highs = [c['high'] for c in candles_1h[-20:]]
    last20_lows = [c['low'] for c in candles_1h[-20:]]

    hh = last20_highs[-1] > last20_highs[0]
    hl = last20_lows[-1] > last20_lows[0]
    lh = last20_highs[-1] < last20_highs[0]
    ll = last20_lows[-1] < last20_lows[0]

    if hh and hl: return "BULLISH" # Uptrend
    if lh and ll: return "BEARISH" # Downtrend
    return "RANGE" # Sideways

# ====== ICT LOGIC ======
def detect_sweep(candles):
    if len(candles) < 3: return None
    last3 = candles[-3:]
    high = max(c['high'] for c in last3)
    low = min(c['low'] for c in last3)
    close = candles[-1]['close']

    if close > high and candles[-1]['low'] < high: return {'type': 'BSL', 'level': high}
    if close < low and candles[-1]['high'] > low: return {'type': 'SSL', 'level': low}
    return None

def detect_choch(candles):
    if len(candles) < 3: return None
    h1, h2, h3 = candles[-3]['high'], candles[-2]['high'], candles[-1]['high']
    l1, l2, l3 = candles[-3]['low'], candles[-2]['low'], candles[-1]['low']

    if l3 > l2 > l1 and h3 > h2: return 'BULLISH_CHOCH'
    if h3 < h2 < h1 and l3 < l2: return 'BEARISH_CHOCH'
    return None

def detect_displacement(candles):
    if len(candles) < 2: return None
    body = abs(candles[-1]['close'] - candles[-1]['open'])
    range_ = candles[-1]['high'] - candles[-1]['low']
    if range_ == 0: return None
    if body / range_ > 0.7:
        return 'BULLISH_DISP' if candles[-1]['close'] > candles[-1]['open'] else 'BEARISH_DISP'
    return None

def detect_fvg(candles):
    if len(candles) < 3: return None
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    if c1['high'] < c3['low']: return {'type': 'BULLISH_FVG', 'top': c3['low'], 'bottom': c1['high']}
    if c1['low'] > c3['high']: return {'type': 'BEARISH_FVG', 'top': c1['low'], 'bottom': c3['high']}
    return None

def in_killzone():
    now = datetime.now(TZ).time()
    london = dtime(12, 30) <= now <= dtime(16, 30)
    ny = dtime(19, 30) <= now <= dtime(23, 30)
    return london or ny

def get_point_size(symbol):
    if 'XAU' in symbol: return 0.01
    elif 'USDT' in symbol: return 1.0
    else: return 0.0001

# ====== MAIN CHECK ======
def check_symbol(symbol):
    try:
        # 1. Data 2ක්ම ගන්නවා: 15m for ICT, 1h for Trend
        candles_15m = fetch_ohlcv(symbol, "15min")
        candles_1h = fetch_ohlcv(symbol, "1h")

        if len(candles_15m) < 10 or len(candles_1h) < 20: return

        price = candles_15m[-1]['close']
        trend_1h = get_elliott_trend(candles_1h) # <--- අලුත් Filter

        # KILLZONE ONLY SIGNAL - නැත්නම් return
        if not in_killzone():
            return

        sweep = detect_sweep(candles_15m)
        choch = detect_choch(candles_15m)
        disp = detect_displacement(candles_15m)
        fvg = detect_fvg(candles_15m)
        pt = get_point_size(symbol)

        signal_id = None
        msg = None

        # BULLISH FULL SETUP + TREND CONFIRM
        if sweep and sweep['type'] == 'SSL' and choch == 'BULLISH_CHOCH' and disp == 'BULLISH_DISP' and fvg and fvg['type'] == 'BULLISH_FVG' and trend_1h == "BULLISH":
            signal_id = f"{symbol}_BULL_{candles_15m[-1]['time']}"
            entry = (fvg['bottom'] + fvg['top']) / 2
            sl = entry - POINTS_SL * pt
            tp = entry + POINTS_TP * pt

            msg = f"""🟢 <b>BULLISH ICT + ELLIOTT CONFLUENCE</b>
Pair: {symbol}
Time: {datetime.now(TZ).strftime('%H:%M:%S')}
1H Trend: <b>BULLISH</b> ✅
Entry: {entry:.4f}
SL: {sl:.4f} [-{POINTS_SL} pts]
TP: {tp:.4f} [+{POINTS_TP} pts]
RR: 1:{POINTS_TP/POINTS_SL:.2f}
Sweep: {sweep['level']:.4f}
Killzone: ✅ Yes"""

        # BEARISH FULL SETUP + TREND CONFIRM
        elif sweep and sweep['type'] == 'BSL' and choch == 'BEARISH_CHOCH' and disp == 'BEARISH_DISP' and fvg and fvg['type'] == 'BEARISH_FVG' and trend_1h == "BEARISH":
            signal_id = f"{symbol}_BEAR_{candles_15m[-1]['time']}"
            entry = (fvg['bottom'] + fvg['top']) / 2
            sl = entry + POINTS_SL * pt
            tp = entry - POINTS_TP * pt

            msg = f"""🔴 <b>BEARISH ICT + ELLIOTT CONFLUENCE</b>
Pair: {symbol}
Time: {datetime.now(TZ).strftime('%H:%M:%S')}
1H Trend: <b>BEARISH</b> ✅
Entry: {entry:.4f}
SL: {sl:.4f} [+{POINTS_SL} pts]
TP: {tp:.4f} [-{POINTS_TP} pts]
RR: 1:{POINTS_TP/POINTS_SL:.2f}
Sweep: {sweep['level']:.4f}
Killzone: ✅ Yes"""

        if signal_id and signal_id not in sent_signals:
            send_telegram(msg)
            sent_signals.add(signal_id)
            print(f"Signal sent: {signal_id}")

    except Exception as e:
        print(f"Error {symbol}: {e}")

# ====== RUN LOOP ======
if __name__ == "__main__":
    send_telegram(f"🤖 ICT + Elliott Bot Started\nPairs: {len(SYMBOLS)}\nMode: Killzone Only")
    while True:
        print(f"Scanning... {datetime.now(TZ).strftime('%H:%M:%S')}")
        for sym in SYMBOLS:
            check_symbol(sym)
            time.sleep(3) # API limit නිසා 3s
        time.sleep(CHECK_INTERVAL)
