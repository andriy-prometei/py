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
  1382.5 с   binance
  1214.0 с   bitmart
   977.8 с   toobit
   955.3 с   xt
   921.1 с   phemex
   858.0 с   coinbase
   828.7 с   coinex
   800.3 с   coinbaseadvanced
   788.4 с   huobi
   758.6 с   bingx
   754.7 с   htx
   647.4 с   bydfi
   643.6 с   kucoin
   542.9 с   mexc
   476.3 с   coinbaseexchange
   415.0 с   ascendex
   373.4 с   blofin
   361.6 с   upbit
   333.1 с   kraken
   332.0 с   aster
   265.0 с   whitebit
   253.8 с   bitget
   243.9 с   okxus
   232.9 с   gateio
   224.0 с   gate
   216.7 с   cryptocom
   214.9 с   bitso
   196.2 с   backpack
   193.3 с   independentreserve
   136.7 с   okx
   131.6 с   blockchaincom
   126.9 с   apex
   123.2 с   bybit
   116.2 с   arkham
   115.5 с   bigone
   105.8 с   bitrue
   104.4 с   cryptomus
   104.0 с   hashkey
   100.9 с   digifinex
    98.6 с   ndax
    94.8 с   latoken
    88.9 с   myokx
    87.2 с   bitfinex
    83.4 с   deribit
    81.4 с   poloniex
    59.8 с   derive
    55.7 с   hitbtc
    55.5 с   alp
    54.8 с   hollaex
    52.6 с   cex
    50.7 с   bitmex
    44.0 с   coinsph
    41.2 с   onetrading
    41.1 с   fmfwio
    40.6 с   bitstamp
    38.3 с   coinbaseinternational
    38.1 с   timex
    37.8 с   zaif
    35.4 с   deepcoin
    34.8 с   bitteam
    33.9 с   bitopro
    33.8 с   foxbit
    28.0 с   defx
    27.8 с   novadax
    27.1 с   coinspot
    23.4 с   coincatch
    22.7 с   wavesexchange
    22.6 с   delta
    21.8 с   bequant
    19.3 с   bitbns
    18.3 с   lbank
    15.8 с   modetrade
    15.4 с   btcturk
    14.3 с   p2b
    13.9 с   paradex
    13.2 с   exmo
    10.7 с   dydx
    10.4 с   bit2c
     6.1 с   woo
     6.1 с   woofipro
     5.3 с   indodax
     5.2 с   btcbox
     4.9 с   gemini
     3.8 с   btcmarkets
     3.5 с   zonda
     3.1 с   bittrade
     2.8 с   zebpay
     2.8 с   bithumb
     2.5 с   coinone
     2.5 с   mercado
     2.4 с   oxfun
     2.4 с   binanceus
     2.4 с   bitvavo
     2.3 с   paymium
     2.2 с   bullish
     2.1 с   hibachi
     2.0 с   coincheck
     1.9 с   luno
     1.7 с   bitbank
     1.6 с   bitflyer
     0.9 с   alpaca
====================
"""

# використання
WHITELIST = []#['ascendex', 'aster', 'backpack', 'binance', 'bingx', 'bitfinex', 'bitget', 'bitmart', 'bitmex', 'bybit', 'bydfi', 'coinbase', 'coinex', 'deribit', 'digifinex', 'hashkey', 'huobi', 'gate', 'kraken', 'kucoin', 'lbank', 'mexc', 'okx', 'poloniex', 'toobit', 'woo', 'whitebit', 'xt'] # якщо заповнити — запускатимуться ТІЛЬКИ ці біржі
BLACKLIST = [
    #'binancecoinm', 'binanceus',
    #'testnet', 'sandbox', 'demo',   # тестові
    #'okxus', 'myokx', #okx aliases
    #'gateio', # alias to gate
    #'coinbaseadvanced', 'coinbaseinternational', 'coinbaseexchange', # alias to coinbase
    'hyperliquid', 'tokocrypto', 'yobit', # slow data extraction
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

            raw = info or {}

            # ---- next funding timestamp fallback ----
            if parsed.get("nextFundingTimestamp") is None:
                next_update = raw.get("nextUpdate")
                if next_update:
                    try:
                        ts = int(next_update)
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
    # DELTA
    # ===========
    if hasattr(ccxt, "delta"):
        original_delta = ccxt.delta.parse_funding_rate

        def patched_delta(self, info, market=None):
            parsed = original_delta(self, info, market)

            raw = info or {}
            quotes = raw.get("quotes") or {}

            best_bid = quotes.get("best_bid")
            best_ask = quotes.get("best_ask")
            bid_size = quotes.get("bid_size")
            ask_size = quotes.get("ask_size")

            # ---- price ----
            if best_bid is not None:
                try:
                    parsed["bid"] = float(best_bid)
                except Exception:
                    pass

            if best_ask is not None:
                try:
                    parsed["ask"] = float(best_ask)
                except Exception:
                    pass

            # ---- volumes ----
            if bid_size is not None:
                try:
                    parsed["bid_vol"] = float(bid_size)
                except Exception:
                    pass

            if ask_size is not None:
                try:
                    parsed["ask_vol"] = float(ask_size)
                except Exception:
                    pass

            return parsed

        ccxt.delta.parse_funding_rate = patched_delta

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
    # PHEMEX
    # ===========
    if hasattr(ccxt, "phemex"):
        original_phemex = ccxt.phemex.parse_funding_rate

        def patched_phemex(self, info, market=None):
            parsed = original_phemex(self, info, market)

            raw = info or {}

            bid_ep = raw.get("bidEp")
            ask_ep = raw.get("askEp")

            # Phemex prices are Ep = price * 1e4
            scale = 10000.0

            if bid_ep is not None:
                try:
                    parsed["bid"] = float(bid_ep) / scale
                except Exception:
                    pass

            if ask_ep is not None:
                try:
                    parsed["ask"] = float(ask_ep) / scale
                except Exception:
                    pass

            return parsed

        ccxt.phemex.parse_funding_rate = patched_phemex

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

        if elapsed >= 180:
            print_after_10min = True

        if print_after_10min and int(elapsed) % 60 == 0:
            cur_state = frozenset(active_tasks)

            if cur_state != prev_active_tasks:
                now_str = datetime.now().strftime("%H:%M:%S")
                active_list = sorted(active_tasks) if active_tasks else ["немає"]
                
                if len(active_list) <= 5:
                    active_str = ", ".join(active_list)
                else:
                    active_str = f"({', '.join(active_list[:10])}...)"
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

# ==== helper for next funding time ====
def extract_next_funding_ts(data):
    if not data:
        return None

    # порядок важливий — найчастіші ключі ставимо першими
    keys = (
        'nextFundingTime',
        'nextFundingTimestamp',
        'fundingTimestamp',
        'nextSettleTime',
        'fundingNext',
        'nextFunding',
        'fundingTimeNext',
        'settleTime',
    )

    next_ts = None

    # 1️⃣ перевірка верхнього рівня
    for k in keys:
        v = data.get(k)
        if v:
            next_ts = v
            break

    # 2️⃣ якщо не знайшли — дивимось у info
    if next_ts is None:
        info = data.get('info')
        if isinstance(info, dict):
            for k in keys:
                v = info.get(k)
                if v:
                    next_ts = v
                    break

    if next_ts is None:
        return None

    # 3️⃣ швидка безпечна конвертація
    try:
        ts_val = float(next_ts)
    except (TypeError, ValueError):
        return None

    # якщо мілісекунди
    if ts_val > 1e11:
        ts_val /= 1000

    return int(ts_val)

# ==== Основна функція збору даних ====
def fetch_exchange_data(exchange_name):

    start_time = time.perf_counter()

    try:
        if exchange_name in EXCHANGE_PAIRS.values():
            return []

        timestamp = datetime.now(timezone.utc).isoformat()

        spot_class_name = exchange_name
        futures_class_name = EXCHANGE_PAIRS.get(exchange_name)

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

        spot_markets = spot_ex.load_markets()
        futures_markets = futures_ex.load_markets()

        perpetual_markets = {
            s: m for s, m in futures_markets.items()
            if m.get('swap') and m.get('contract') and m.get('active', True)
        }

        # ==== BULK FUNDING COLLECTION ===

        funding_cache = {}
        funding_disabled = False

        try:
            bulk = futures_ex.fetch_funding_rates()
            if bulk and isinstance(bulk, dict):
                funding_cache = bulk
        except Exception:
            pass

        # --- fallback на перші 10 ---
        if not funding_cache:
            zero_count = 0
            bad_next_count = 0
            tested = 0

            for symbol in list(perpetual_markets.keys())[:10]:
                try:
                    fr = futures_ex.fetch_funding_rate(symbol)
                    if not fr:
                        continue

                    funding_cache[symbol] = fr
                    tested += 1

                    rate = fr.get("fundingRate") or fr.get("lastFundingRate")
                    next_ts = extract_next_funding_ts(fr)

                    if not rate or float(rate) == 0:
                        zero_count += 1

                    if not next_ts:
                        bad_next_count += 1
                    else:
                        ts_val = float(next_ts)
                        if ts_val < time.time():
                            bad_next_count += 1

                except Exception:
                    continue

            if tested == 0 or (
                tested >= 10 and
                zero_count >= 10 and
                bad_next_count >= 10
            ):
                funding_disabled = True

        # === BULK TICKERS ===

        futures_tickers = {}
        spot_tickers = {}
        
        try:
            ft = futures_ex.fetch_tickers()
            if isinstance(ft, dict):
                futures_tickers = ft
        except Exception:
            pass
        
        try:
            st = spot_ex.fetch_tickers()
            if isinstance(st, dict):
                spot_tickers = st
        except Exception:
            pass

        symbol_data = {}

        # === FUTURES ===

        for perp_symbol, perp_market in perpetual_markets.items():

            base = perp_market["base"]
            quote = perp_market["quote"]
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

            # ---- FUNDING ---
            if not funding_disabled:
                fr_data = funding_cache.get(perp_symbol)

                if not fr_data:
                    try:
                        fr_data = futures_ex.fetch_funding_rate(perp_symbol)
                        funding_cache[perp_symbol] = fr_data
                    except Exception:
                        fr_data = None

                if fr_data:
                    rate = fr_data.get("fundingRate") or fr_data.get("lastFundingRate")
                    if rate:
                        row["funding_rate"] = float(rate)

                    next_ts = extract_next_funding_ts(fr_data)
                    if next_ts:
                        ts_val = float(next_ts)
                        next_dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
                        row["next_funding_utc"] = next_dt.isoformat()
                        row["countdown_sec"] = int(
                            (next_dt - datetime.now(timezone.utc)).total_seconds()
                        )

                    # пробуємо bid/ask з funding
                    row["futures_bid"] = fr_data.get("bid") or row["futures_bid"]
                    row["futures_ask"] = fr_data.get("ask") or row["futures_ask"]

            # --- FUTURES PRICE ---
            if row["futures_bid"] is None or row["futures_ask"] is None:
                # Спочатку перевіряємо bulk-тікери
                ticker = futures_tickers.get(perp_symbol)
                if ticker and (ticker.get("bid") is not None or ticker.get("ask") is not None):
                    if row["futures_bid"] is None:
                        row["futures_bid"] = ticker.get("bid")
                    if row["futures_ask"] is None:
                        row["futures_ask"] = ticker.get("ask")
                else:
                    # Якщо немає – індивідуальний запит
                    try:
                        ticker_ind = futures_ex.fetch_ticker(perp_symbol)
                        if ticker_ind:
                            if row["futures_bid"] is None:
                                row["futures_bid"] = ticker_ind.get("bid")
                            if row["futures_ask"] is None:
                                row["futures_ask"] = ticker_ind.get("ask")
                    except Exception:
                        pass

        # === SPOT ===

        for sym, m in spot_markets.items():

            if not m.get("spot"):
                continue

            base = m["base"]
            quote = m["quote"]
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

            row["has_spot"] = True

            # --- SPOT PRICE ---
            if row["spot_bid"] is None or row["spot_ask"] is None:
                # Спочатку перевіряємо bulk-тікери
                ticker = spot_tickers.get(sym)
                if ticker and (ticker.get("bid") is not None or ticker.get("ask") is not None):
                    if row["spot_bid"] is None:
                        row["spot_bid"] = ticker.get("bid")
                    if row["spot_ask"] is None:
                        row["spot_ask"] = ticker.get("ask")
                else:
                    # Якщо немає – індивідуальний запит
                    try:
                        ticker_ind = spot_ex.fetch_ticker(sym)
                        if ticker_ind:
                            if row["spot_bid"] is None:
                                row["spot_bid"] = ticker_ind.get("bid")
                            if row["spot_ask"] is None:
                                row["spot_ask"] = ticker_ind.get("ask")
                    except Exception:
                        pass
        
        results = list(symbol_data.values())

        duration = time.perf_counter() - start_time
        exchange_times[exchange_name] = duration

        logger.info(
            f"{exchange_name:8} {duration:4.1f}s rows={len(results)}"
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
    