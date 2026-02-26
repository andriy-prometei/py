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
   709.2 с   bitmart
   397.7 с   bitget
   375.7 с   binance
   366.0 с   bingx
   365.4 с   mexc
   344.0 с   bybit
   335.7 с   phemex
   322.9 с   gate
   309.5 с   xt
   298.8 с   bydfi
   291.8 с   deepcoin
   267.0 с   kucoin
   246.5 с   aster
   239.1 с   bitmex
   235.2 с   blofin
   216.4 с   kraken
   208.8 с   bitso
   182.7 с   cryptocom
   181.5 с   ascendex
   179.9 с   independentreserve
   171.3 с   htx
   170.2 с   huobi
   150.5 с   okx
   144.3 с   woo
   117.1 с   whitebit
    93.8 с   digifinex
    90.4 с   bitfinex
    88.1 с   ndax
    82.1 с   bitrue
    82.1 с   backpack
    80.2 с   delta
    70.9 с   coinex
    69.4 с   coinbase
    63.1 с   deribit
    57.0 с   cex
    53.1 с   derive
    46.5 с   bigone
    42.3 с   hyperliquid
    38.8 с   coinspot
    35.4 с   coincatch
    33.7 с   zaif
    33.0 с   wavesexchange
    30.7 с   defx
    28.2 с   fmfwio
    24.1 с   btcturk
    21.5 с   bitstamp
    20.5 с   coinsph
    18.3 с   bequant
    17.2 с   hashkey
    16.7 с   apex
    14.5 с   hitbtc
    14.2 с   foxbit
    13.7 с   arkham
    13.5 с   blockchaincom
    13.2 с   bitbns
    13.2 с   exmo
    13.0 с   alp
    12.5 с   bitteam
    11.4 с   poloniex
    11.2 с   bit2c
    10.8 с   cryptomus
     8.8 с   dydx
     8.4 с   bitopro
     7.6 с   latoken
     7.2 с   woofipro
     6.8 с   gemini
     6.6 с   toobit
     5.6 с   timex
     5.2 с   upbit
     4.4 с   hollaex
     4.4 с   onetrading
     3.9 с   modetrade
     3.9 с   paradex
     3.7 с   zebpay
     3.7 с   btcbox
     3.5 с   bullish
     3.4 с   bitvavo
     3.3 с   coinone
     3.2 с   btcmarkets
     3.0 с   bittrade
     2.8 с   coincheck
     2.8 с   zonda
     2.8 с   p2b
     2.4 с   bithumb
     2.3 с   lbank
     2.2 с   novadax
     2.0 с   bitflyer
     1.7 с   alpaca
     1.7 с   bitbank
     1.0 с   indodax
     0.9 с   paymium
     0.5 с   mercado
     0.4 с   oxfun
     0.4 с   luno
     0.4 с   hibachi
====================
"""

# Приклади використання (змініть на свої потреби)
WHITELIST = []#['ascendex', 'aster', 'backpack', 'binance', 'bingx', 'bitfinex', 'bitget', 'bitmart', 'bitmex', 'bybit', 'bydfi', 'coinbase', 'coinex', 'deribit', 'digifinex', 'hashkey', 'huobi', 'hyperliquid', 'gate', 'kraken', 'kucoin', 'lbank', 'mexc', 'okx', 'poloniex', 'toobit', 'woo', 'whitebit', 'xt'] # якщо заповнити — запускатимуться ТІЛЬКИ ці біржі
BLACKLIST = [
    'binancecoinm', 'binanceus',
    'testnet', 'sandbox', 'demo',   # тестові
    'okxus', 'myokx', #okx aliases
    'gateio', # alias to gate
    'coinbaseadvanced', 'coinbaseinternational', 'coinbaseexchange', # alias to coinbase
    'tokocrypto', 'yobit', # slow data extraction
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


def _ts_to_iso(ts_ms: int):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
    

def patch_funding_parsers():
    print("Applying funding parser patches...")

    # ===========
    # BITGET
    # ===========
    if hasattr(ccxt, "bitget"):
        original_bitget = ccxt.bitget.parse_funding_rate

        def patched_bitget(self, info, market=None):
            parsed = original_bitget(self, info, market)

            if isinstance(info, dict) and info.get("nextUpdate"):
                try:
                    ts = int(info["nextUpdate"])
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.bitget.parse_funding_rate = patched_bitget

    # ===========
    # BITMART
    # ===========
    if hasattr(ccxt, "bitmart"):
        original_bitmart = ccxt.bitmart.parse_funding_rate

        def patched_bitmart(self, info, market=None):
            parsed = original_bitmart(self, info, market)

            if isinstance(info, dict) and info.get("funding_time"):
                try:
                    ts = int(info["funding_time"])
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.bitmart.parse_funding_rate = patched_bitmart

    # ===========
    # BITMEX
    # ===========
    if hasattr(ccxt, "bitmex"):
        original_bitmex = ccxt.bitmex.parse_funding_rate

        def patched_bitmex(self, info, market=None):
            parsed = original_bitmex(self, info, market)

            if isinstance(info, dict) and info.get("fundingTimestamp"):
                try:
                    iso = info["fundingTimestamp"]
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    ts = int(dt.timestamp() * 1000)

                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = dt.isoformat()

                except Exception:
                    pass

            return parsed

        ccxt.bitmex.parse_funding_rate = patched_bitmex

    # ===========
    # GATE
    # ===========
    if hasattr(ccxt, "gate"):
        original_gate = ccxt.gate.parse_funding_rate

        def patched_gate(self, info, market=None):
            parsed = original_gate(self, info, market)

            if isinstance(info, dict) and info.get("funding_next_apply"):
                try:
                    ts = int(info["funding_next_apply"]) * 1000
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.gate.parse_funding_rate = patched_gate

    # ===========
    # HUOBI
    # ===========
    if hasattr(ccxt, "huobi"):
        original_huobi = ccxt.huobi.parse_funding_rate

        def patched_huobi(self, info, market=None):
            parsed = original_huobi(self, info, market)

            # fallback якщо CCXT не поставив
            if parsed.get("nextFundingTimestamp") is None:

                ts = info.get("fundingTimestamp") or info.get("nextFundingTime")

                if ts:
                    try:
                        ts = int(ts)
                        parsed["nextFundingTimestamp"] = ts
                        parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                    except Exception:
                        pass

            return parsed

        ccxt.huobi.parse_funding_rate = patched_huobi

    # ===========
    # WHITEBIT
    # ===========
    if hasattr(ccxt, "whitebit"):
        original_whitebit = ccxt.whitebit.parse_funding_rate

        def patched_whitebit(self, info, market=None):
            parsed = original_whitebit(self, info, market)

            # ADD THIS CHECK: Ensure 'parsed' is not None before proceeding
            if parsed is None:
                return None

            if isinstance(info, dict) and info.get("next_funding_rate_timestamp"):
                try:
                    ts = int(info["next_funding_rate_timestamp"])
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.whitebit.parse_funding_rate = patched_whitebit

    # ===========
    # XT
    # ===========
    if hasattr(ccxt, "xt"):
        original_xt = ccxt.xt.parse_funding_rate

        def patched_xt(self, info, market=None):
            parsed = original_xt(self, info, market)

            if isinstance(info, dict) and info.get("nextCollectionTime"):
                try:
                    ts = int(info["nextCollectionTime"])
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.xt.parse_funding_rate = patched_xt

    print("✅ Funding parser patches applied")

# Викликати один раз на початку програми
patch_funding_parsers()


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

        if elapsed >= 300:
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
        'nextFundingTime', 'nextFundingTimestamp', 'fundingTimestamp',
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
            info.get('fundingTimestamp') or
            info.get('nextSettleTime') or
            info.get('fundingNext')
        )

    return next_ts

# ==== Основна функція збору даних ====
def fetch_exchange_data(exchange_name):

    start_time = time.perf_counter()

    try:
        if exchange_name in EXCHANGE_PAIRS.values():
            return []

        timestamp = datetime.now(timezone.utc).isoformat()

        spot_class_name = exchange_name
        futures_class_name = EXCHANGE_PAIRS.get(exchange_name)

        # ========= CLIENTS =========
        
        spot_ex = getattr(ccxt, spot_class_name)({
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {'defaultType': 'spot'}
        })
        futures_ex = getattr(
            ccxt,
            futures_class_name or spot_class_name
        )({
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {'defaultType': 'swap'}
        })

        # ========= MARKETS =========

        spot_markets = spot_ex.load_markets()
        futures_markets = futures_ex.load_markets()
        #print(futures_markets['BTC/USDT:USDT'])

        perpetual_markets = {
            s: m for s, m in futures_markets.items()
            if m.get('swap')
               and m.get('active', True)
               and m.get('contract')
        }

        # ========= FUTURES TICKERS =========

        futures_tickers = {}
        try:
            if futures_ex.has.get('fetchTickers'):
                futures_tickers = futures_ex.fetch_tickers()
        except Exception:
            pass

        # fallback
        if not futures_tickers:
            for s in perpetual_markets:
                try:
                    futures_tickers[s] = futures_ex.fetch_ticker(s)
                except Exception:
                    pass

        # ========= SPOT TICKERS =========

        spot_tickers = {}

        try:
            if spot_ex.has.get('fetchTickers'):
                spot_tickers = spot_ex.fetch_tickers()
        except Exception:
            pass

        if not spot_tickers:
            for s, m in spot_markets.items():
                if not m.get('spot'):
                    continue
                try:
                    spot_tickers[s] = spot_ex.fetch_ticker(s)
                except Exception:
                    pass

        # ========= DATA =========

        symbol_data = {}
        
        # ПЕРЕВІРКА ПІДТРИМКИ FUNDING RATE
        can_fetch_funding = futures_ex.has.get('fetchFundingRate', False)
        if not can_fetch_funding:
            logger.warning(f"{exchange_name} does not support fetchFundingRate()")

        # ---------- FUTURES ----------
        for perp_symbol, perp_market in perpetual_markets.items():

            base = perp_market['base']
            quote = perp_market['quote']
            #norm_symbol = perp_symbol
            norm_symbol = f"{base}/{quote}"

            row = symbol_data.setdefault(norm_symbol, {
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
            })

            # ===== FUTURES PRICE =====

            ticker = futures_tickers.get(perp_symbol)
            if ticker:
                row['futures_bid'] = ticker.get('bid')
                row['futures_ask'] = ticker.get('ask')
                
            #print(ticker)
            #exit()

            # ===== FUNDING SYMBOL MAP =====

            funding_symbol = None

            # пробуємо прямий
            if perp_symbol in futures_ex.markets:
                funding_symbol = perp_symbol

            # пробуємо нормалізований
            elif norm_symbol in futures_ex.markets:
                funding_symbol = norm_symbol

            # пробуємо id
            else:
                mid = perp_market.get('id')
                for s2, m2 in futures_ex.markets.items():
                    if m2.get('id') == mid:
                        funding_symbol = s2
                        break

            # ===== FUNDING =====
            if funding_symbol and can_fetch_funding:
                try:
                    fr_data = futures_ex.fetch_funding_rate(funding_symbol)
                    #print('fr_data', fr_data)
                    #exit()
                    if fr_data is None:
                        continue

                    fr = fr_data.get('fundingRate') \
                         or fr_data.get('lastFundingRate')

                    if fr:
                        row['funding_rate'] = float(fr)

                    next_ts = extract_next_funding_ts(fr_data)

                    if next_ts:
                        ts_value = float(next_ts)
                        divisor = 1000 if ts_value > 1e10 else 1

                        next_dt = datetime.fromtimestamp(
                            ts_value / divisor,
                            tz=timezone.utc
                        )

                        row['next_funding_utc'] = next_dt.isoformat()
                        row['countdown_sec'] = int((next_dt - datetime.now(timezone.utc)).total_seconds())

                except Exception as e:
                    print(f"{exchange_name} funding error:", funding_symbol, str(e)[:120])

        # ---------- SPOT ----------
        for sym, m in spot_markets.items():

            if not m.get('spot'):
                continue

            base = m['base']
            quote = m['quote']
            norm_symbol = f"{base}/{quote}"

            row = symbol_data.setdefault(norm_symbol, {
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
            })

            row['has_spot'] = True

            ticker = spot_tickers.get(sym)
            if ticker:
                row['spot_bid'] = ticker.get('bid')
                row['spot_ask'] = ticker.get('ask')

        results = list(symbol_data.values())

        duration = time.perf_counter() - start_time
        exchange_times[exchange_name] = duration

        both_count = sum(
            1 for r in results if r['has_spot'] and r['has_futures']
        )

        logger.info(
            f"{exchange_name:8} {duration:4.1f}s {len(results):4}/{both_count:3} rows (all/both markets)"
        )

        return results

    except Exception as e:

        duration = time.perf_counter() - start_time
        exchange_times[exchange_name] = duration

        logger.error(
            f"{exchange_name} failed after {duration:.1f}s: {str(e)[:180]}"
        )

        return []
        

# ==== Основна функція ====
def main():
    global done
    
    start_time = time.time()
    logger.info("Запуск збору funding + spot")

    build_exchange_pairs()
    
    to_run = get_exchanges_to_run()
    if len(to_run) <= 10:
        display = ', '.join(to_run)
    else:
        display = ', '.join(to_run[:5] + ['..'] + to_run[-5:])
    logger.info(f"Біржі для обробки ({len(to_run)}): {display}")

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
                    all_rows.extend(data[:2])
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
    