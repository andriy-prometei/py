import ccxt
import decimal
import csv
import os
import sys
import time
import logging
from datetime import datetime, timezone
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

"""
====================
за часом обробки (секунди):
--------------------
  1995.9 с   tokocrypto
  1965.9 с   mexc
  1831.9 с   gate
  1749.5 с   bitmart
  1735.0 с   lbank
  1612.7 с   bingx
  1302.1 с   phemex
  1285.6 с   htx
  1284.3 с   bitget
  1272.6 с   latoken
  1271.8 с   huobi
  1203.7 с   toobit
  1192.6 с   xt
  1192.0 с   bitrue
  1049.3 с   bybit
   910.1 с   ascendex
   871.3 с   deepcoin
   815.5 с   coinex
   789.7 с   kucoin
   777.2 с   kraken
   767.4 с   cryptocom
   759.0 с   coinbase
   726.7 с   okx
   726.3 с   binance
   535.3 с   poloniex
   512.3 с   bydfi
   508.4 с   bigone
   506.5 с   cex
   501.6 с   hitbtc
   462.0 с   blofin
   429.6 с   aster
   395.7 с   bitmex
   349.2 с   digifinex
   335.3 с   upbit
   333.4 с   whitebit
   320.3 с   novadax
   297.8 с   bitfinex
   285.5 с   bitbns
   262.5 с   coinbaseexchange
   250.9 с   fmfwio
   211.0 с   btcturk
   200.4 с   bitso
   181.4 с   independentreserve
   181.0 с   zonda
   164.9 с   woo
   138.7 с   p2b
   127.7 с   backpack
   121.7 с   exmo
    94.6 с   bitstamp
    93.4 с   hashkey
    91.9 с   ndax
    90.7 с   foxbit
    90.0 с   blockchaincom
    88.3 с   coinsph
    88.1 с   delta
    84.4 с   timex
    61.7 с   arkham
    59.7 с   cryptomus
    58.1 с   bequant
    57.7 с   apex
    47.9 с   hollaex
    44.3 с   bitteam
    37.3 с   derive
    34.8 с   onetrading
    34.5 с   alp
    28.7 с   zaif
    24.9 с   bitopro
    16.5 с   defx
    16.4 с   coinspot
    12.7 с   wavesexchange
    10.1 с   bit2c
     6.4 с   gemini
     6.2 с   modetrade
     6.0 с   deribit
     4.2 с   paradex
     4.0 с   coincatch
     3.8 с   zebpay
     3.3 с   dydx
     3.0 с   paymium
     2.3 с   mercado
     2.1 с   oxfun
     1.9 с   luno
     1.7 с   coincheck
     1.6 с   indodax
     1.6 с   bithumb
     1.6 с   woofipro
     1.6 с   hibachi
     1.3 с   binanceus
     1.2 с   bittrade
     1.1 с   btcbox
     1.0 с   bitvavo
     0.9 с   bitbank
     0.9 с   bitflyer
     0.9 с   coinone
     0.6 с   bullish
     0.4 с   btcmarkets
     0.2 с   alpaca
====================

====================
за часом обробки (секунди):
--------------------
  2245.0 с   kraken
  1876.0 с   lbank
  1747.0 с   gate
  1697.9 с   mexc
  1643.8 с   bitmart
  1419.8 с   binance
  1286.5 с   toobit
  1259.0 с   kucoin
  1192.5 с   bitget
  1120.5 с   bingx
   985.6 с   xt
   944.2 с   bybit
   849.5 с   coinbase
   821.2 с   okx
   819.7 с   coinex
   765.4 с   ascendex
   752.9 с   huobi
   621.7 с   poloniex
   597.8 с   bydfi
   508.4 с   aster
   496.1 с   whitebit
   416.6 с   bitmex
   316.3 с   bitfinex
   275.7 с   woo
   190.3 с   digifinex
   127.2 с   backpack
    94.5 с   hashkey
    49.0 с   deribit
====================
"""

# Приклади використання (змініть на свої потреби)
WHITELIST = ['ascendex', 'aster', 'backpack', 'binance', 'bingx', 'bitfinex', 'bitget', 'bitmart', 'bitmex', 'bybit', 'bydfi', 'coinbase', 'coinex', 'deribit', 'digifinex', 'hashkey', 'huobi', 'gate', 'kraken', 'kucoin', 'lbank', 'mexc', 'okx', 'poloniex', 'toobit', 'woo', 'whitebit', 'xt'] # якщо заповнити — запускатимуться ТІЛЬКИ ці біржі
BLACKLIST = [
    'binancecoinm', 'binanceus',
    'testnet', 'sandbox', 'demo',   # тестові
    'okxus', 'myokx', #okx aliases
    'gateio', # alias to gate
    'coinbaseadvanced', 'coinbaseinternational', # alias to coinbase
    'hyperliquid', 'yobit', # slow data extraction
]

# Автоматичні пропуски (futures-класи, які дублюють unified)
AUTO_SKIP_SUFFIX = ['futures', 'usdm', 'coinm', 'swap', 'test', 'sandbox', 'demo']

def get_exchanges_to_run():
    all_ex = ccxt.exchanges
    
    # 1. Базовий фільтр: пропускаємо очевидні futures-дублі та тестові
    candidates = [
        ex for ex in all_ex
        if not any(suf.lower() in ex.lower() for suf in AUTO_SKIP_SUFFIX)
    ]
    
    # 2. Застосовуємо BLACKLIST (виключаємо)
    if BLACKLIST:
        candidates = [
            ex for ex in candidates
            if ex.lower() not in (b.lower() for b in BLACKLIST)
        ]
    
    # 3. Застосовуємо WHITELIST (якщо є — тільки вони)
    if WHITELIST:
        whitelist_lower = {w.lower() for w in WHITELIST}
        candidates = [
            ex for ex in candidates
            if ex.lower() in whitelist_lower
        ]
    
    return sorted(candidates)


# Глобальні змінні для моніторингу
exchange_times = {}  # exchange_name → seconds
active_tasks = set() # які біржі обробляються
prev_active_tasks = frozenset()  # попередній стан (frozenset бо множину не можна хешувати)
done = False # Флаг, щоб моніторинговий потік знав, коли завершувати

def monitoring_thread():
    global prev_active_tasks
    
    start_time = time.time()
    print_after_10min = False

    while not done:
        elapsed = time.time() - start_time

        if elapsed >= 600:
            print_after_10min = True

        if print_after_10min and int(elapsed) % 60 == 0:
            cur_state = frozenset(active_tasks)

            if cur_state != prev_active_tasks:
                now_str = datetime.now().strftime("%H:%M:%S")
                active_list = sorted(active_tasks) if active_tasks else ["немає"]
                
                if len(active_list) <= 5:
                    active_str = ", ".join(active_list)
                else:
                    active_str = f"{len(active_list)} бірж ({', '.join(active_list[:5])}...)"
                print(f"[{now_str}] Залишилось ({len(active_tasks)}): {active_str}")


                # оновлюємо попередній стан
                prev_active_tasks = cur_state

        time.sleep(1)


# ==== Налаштування логування ====
log_file = 'funding_collector.log'
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

fh = logging.FileHandler(log_file)
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
logger.addHandler(fh)

# ==== Контроль одночасного запуску ====
PID_FILE = 'funding_collector.pid'

def is_process_running(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

if os.path.exists(PID_FILE):
    with open(PID_FILE, 'r') as f:
        pid = int(f.read())
        if is_process_running(pid):
            logger.info("Script already running. Exiting.")
            sys.exit(0)
    logger.info("Old PID file found but process not running. Overwriting.")

with open(PID_FILE, 'w') as f:
    f.write(str(os.getpid()))

# ==== Словник пар (spot_class → futures_class) ====
EXCHANGE_PAIRS = {
    'kucoin': 'kucoinfutures',
    'binance': 'binanceusdm',      # USDT-M futures
    # 'binancecoinm': None,        # якщо хочеш обробляти окремо — можна додати
    # 'okx': None,                 # unified
    # 'bybit': None,
    # 'gate': None,
}

def build_exchange_pairs():
    global EXCHANGE_PAIRS
    exchanges = set(ccxt.exchanges)
    futures_suffixes = ['futures', 'usdm', 'coinm']

    for ex in list(exchanges):
        lower = ex.lower()
        if any(suffix in lower for suffix in futures_suffixes):
            base = ex
            for suf in futures_suffixes:
                if lower.endswith(suf):
                    base = ex[:-len(suf)].rstrip()
                    break
            if base in exchanges and base != ex:
                if base not in EXCHANGE_PAIRS:
                    EXCHANGE_PAIRS[base] = ex

    logger.info(f"Виявлені пари бірж (spot → futures): {EXCHANGE_PAIRS}")

# ==== Допоміжна функція для next funding time ====
def extract_next_funding_ts(data):
    next_ts = None
    for k in [
        'nextFundingTime', 'nextFundingTimestamp',
        'nextSettleTime', 'fundingNext', 'nextFunding',
        'fundingTimeNext', 'settleTime'
    ]:
        if k in data and data[k]:
            next_ts = data[k]
            break

    if next_ts is None and 'info' in data:
        info = data['info']
        next_ts = (
            info.get('nextFundingTime') or
            info.get('nextFundingTimestamp') or
            info.get('nextSettleTime') or
            info.get('fundingNext')
        )

    return next_ts

# ==== Основна функція збору даних ====
def fetch_exchange_data(exchange_name):
    """
    Збирає funding rate, next funding time та bid/ask для perpetual swaps + spot на біржі.
    Підтримує випадки, коли spot та futures — різні класи (наприклад binance → binanceusdm).
    """
    start_time = time.perf_counter()
    try:
        # Пропускаємо чисті futures-класи, якщо вони вже оброблені через пару
        if exchange_name in EXCHANGE_PAIRS.values():
            logger.debug(f"Пропускаємо окремий запуск futures-класу: {exchange_name}")
            return []

        timestamp = datetime.now(timezone.utc).isoformat()

        # Визначаємо класи
        spot_class_name   = exchange_name
        futures_class_name = EXCHANGE_PAIRS.get(exchange_name)

        # Ініціалізуємо екземпляри
        spot_ex = None
        futures_ex = None

        if spot_class_name:
            spot_ex = getattr(ccxt, spot_class_name)({
                'enableRateLimit': True,
                'timeout': 30000,
            })

        if futures_class_name:
            futures_ex = getattr(ccxt, futures_class_name)({
                'enableRateLimit': True,
                'timeout': 30000,
                'options': {'defaultType': 'swap'},
            })

        # Якщо немає futures — використовуємо spot як основний для ф’ючерсів (okx, bybit, gate тощо)
        main_futures_ex = futures_ex or spot_ex
        if not main_futures_ex:
            logger.warning(f"Не вдалося створити екземпляр біржі для {exchange_name}")
            return []

        # Завантажуємо ринки РІЗНО для spot та futures
        spot_markets   = spot_ex.load_markets()   if spot_ex   else {}
        futures_markets = main_futures_ex.load_markets()

        # Фільтруємо тільки активні perpetual swaps (безстрокові)
        perpetual_markets = {
            s: m for s, m in futures_markets.items()
            if m.get('swap') 
               and m.get('active', True) 
               and not m.get('expiry')           # безстрокові
               and m['contract']                 # додаткова перевірка
        }

        # Словник для нормалізованих символів (BTC/USDT тощо)
        symbol_data = {}  # "BTC/USDT" → рядок даних

        # ─── 1. Спочатку збираємо дані по perpetual futures ───
        for perp_symbol, perp_market in perpetual_markets.items():
            base  = perp_market['base']
            quote = perp_market['quote']
            norm_symbol = f"{base}/{quote}"

            if norm_symbol not in symbol_data:
                symbol_data[norm_symbol] = {
                    'exchange': exchange_name,
                    'symbol': norm_symbol,
                    'funding_rate': None,
                    'next_funding_utc': None,
                    'countdown_sec': None,
                    'spot_bid': None,
                    'spot_ask': None,
                    'futures_bid': None,
                    'futures_ask': None,
                    'has_spot': False,
                    'has_futures': True,
                    'funding_timestamp_utc': timestamp
                }

            row = symbol_data[norm_symbol]

            # Funding rate + наступний funding
            try:
                fr_ex = main_futures_ex
                fr_data = fr_ex.fetch_funding_rate(perp_symbol)
                fr = decimal.Decimal(str(fr_data.get('fundingRate') or fr_data.get('lastFundingRate') or 0))
                if fr != 0:
                    row['funding_rate'] = float(fr)

                next_ts = extract_next_funding_ts(fr_data)
                if next_ts:
                    ts_value = float(next_ts)
                    divisor = 1000 if ts_value > 1e10 else 1
                    next_dt = datetime.fromtimestamp(ts_value / divisor, tz=timezone.utc)
                    countdown = max(0, (next_dt - datetime.now(timezone.utc)).total_seconds())
                    row['next_funding_utc'] = next_dt.isoformat()
                    row['countdown_sec'] = countdown
            except Exception as e:
                logger.debug(f"Funding rate error {perp_symbol} on {exchange_name}: {e}")

            # Futures bid/ask
            try:
                ticker = main_futures_ex.fetch_ticker(perp_symbol)
                row['futures_bid'] = ticker.get('bid')
                row['futures_ask'] = ticker.get('ask')
            except Exception:
                pass

        # ─── 2. Додаємо/оновлюємо spot-ринки ───
        for sym, m in spot_markets.items():
            if not m.get('spot') or not m.get('active', True):
                continue

            base  = m['base']
            quote = m['quote']
            norm_symbol = f"{base}/{quote}"

            if norm_symbol not in symbol_data:
                symbol_data[norm_symbol] = {
                    'exchange': exchange_name,
                    'symbol': norm_symbol,
                    'funding_rate': None,
                    'next_funding_utc': None,
                    'countdown_sec': None,
                    'spot_bid': None,
                    'spot_ask': None,
                    'futures_bid': None,
                    'futures_ask': None,
                    'has_spot': True,
                    'has_futures': False,
                    'funding_timestamp_utc': timestamp
                }

            row = symbol_data[norm_symbol]
            row['has_spot'] = True

            # Spot bid/ask
            try:
                spot_ticker = spot_ex.fetch_ticker(sym)
                row['spot_bid'] = spot_ticker.get('bid')
                row['spot_ask'] = spot_ticker.get('ask')
            except Exception:
                pass

        # ─── 3. Перетворюємо в список ───
        results = list(symbol_data.values())

        duration = time.perf_counter() - start_time
        exchange_times[exchange_name] = duration

        both_count = sum(1 for r in results if r['has_spot'] and r['has_futures'])
        logger.info(f"{exchange_name:12} {duration:6.1f}s   rows: {len(results):5} "
                    f"(з обома ринками: {both_count:4})")

        return results

    except Exception as e:
        duration = time.perf_counter() - start_time
        exchange_times[exchange_name] = duration
        logger.error(f"{exchange_name} failed after {duration:.1f}s: {str(e)[:180]}")
        return []
        

# ==== Основна функція ====
def main():
    global done
    
    start_time = time.time()
    logger.info("Запуск збору funding + spot")

    build_exchange_pairs()
    
    to_run = get_exchanges_to_run()
    logger.info(f"Бірж для обробки: {len(to_run)} → {', '.join(to_run[:5]  +  ['..' ]+ to_run[-5:])}")

    # Запускаємо моніторинговий потік
    monitor = threading.Thread(target=monitoring_thread, daemon=True)
    monitor.start()

    all_rows = []
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {}
        for ex in to_run:
            active_tasks.add(ex)
            fut = executor.submit(fetch_exchange_data, ex)
            futures[fut] = ex

        for future in as_completed(futures):
            ex = futures[future]
            try:
                data = future.result()
                if data:
                    all_rows.extend(data)
                    #logger.info(f"{ex}: {len(data)} recs")
            except Exception as e:
                logger.error(f"{ex}: помилка {e}")
            finally:
                active_tasks.discard(ex)

    done = True  # зупиняємо моніторинг
    
    # Після обробки всіх бірж
    if exchange_times:
        sorted_exchanges = sorted(
            exchange_times.items(),
            key=lambda x: x[1],
            reverse=True
        )

        print("\n" + "="*20)
        print("за часом обробки (секунди):")
        print("-"*20)
        for ex, sec in sorted_exchanges:
            print(f"{sec:8.1f} с   {ex}")
        print("="*20 + "\n")

    ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    folder = 'funding_results'
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, f'funding_{ts_str}.csv')

    fieldnames = [
        'exchange', 'symbol',
        'funding_rate', 'next_funding_utc', 'countdown_sec',
        'spot_bid', 'spot_ask', 'futures_bid', 'futures_ask',
        'has_spot', 'has_futures', 'funding_timestamp_utc'
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    duration = time.time() - start_time
    logger.info(f"Завершено. Час: {duration:.1f} с, recs: {len(all_rows)}")

    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

if __name__ == "__main__":
    main()
    