import ccxt
import decimal
import csv
import os
import sys
import time
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==== Налаштування логування ====
log_file = 'funding_collector.log'
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Консольний хендлер
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Файловий хендлер
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
    else:
        return True

if os.path.exists(PID_FILE):
    with open(PID_FILE, 'r') as f:
        pid = int(f.read())
        if is_process_running(pid):
            logger.info("Script already running. Exiting.")
            sys.exit(0)
        else:
            logger.info("Previous PID file exists but process not running. Overwriting.")

with open(PID_FILE, 'w') as f:
    f.write(str(os.getpid()))

# ==== Функції для збору funding rate ====
def fetch_funding(exchange_name):
    try:
        exchange_class = getattr(ccxt, exchange_name)
        exchange = exchange_class({'enableRateLimit': True})
        if not hasattr(exchange, 'fetch_funding_rate'):
            return []  # Біржа не підтримує funding
        results = []
        markets = exchange.load_markets()
        for symbol, m in markets.items():
            try:
                if m.get('future') or m.get('contract') or m.get('linear') or m.get('inverse'):
                    fr = None
                    next_ts = None
                    try:
                        data = exchange.fetch_funding_rate(symbol)
                        fr = decimal.Decimal(data.get('fundingRate', 0))
                        next_ts = data.get('nextFundingTime', None)
                    except Exception:
                        continue
                    timestamp = datetime.now(timezone.utc).isoformat()
                    countdown = None
                    if next_ts:
                        try:
                            countdown = (datetime.fromtimestamp(int(next_ts)/1000, tz=timezone.utc) - datetime.now(timezone.utc)).total_seconds()
                        except Exception:
                            countdown = None
                    results.append({
                        'exchange': exchange_name,
                        'symbol': symbol,
                        'funding_rate': float(fr) if fr else 0,
                        'next_funding_utc': datetime.fromtimestamp(int(next_ts)/1000, tz=timezone.utc).isoformat() if next_ts else None,
                        'countdown_sec': countdown,
                        'funding_timestamp_utc': timestamp
                    })
            except Exception:
                continue
        return results
    except Exception as e:
        logger.error(f"Failed to fetch funding for {exchange_name}: {e}")
        return []

# ==== Основна функція ====
def main():
    start_time = time.time()
    logger.info("Funding collection started")
    exchanges = ccxt.exchanges
    all_results = []

    with ThreadPoolExecutor(max_workers=20) as executor:  # 10 потоків
        futures = {executor.submit(fetch_funding, ex): ex for ex in exchanges}
        for future in as_completed(futures):
            ex = futures[future]
            try:
                data = future.result()
                if data:
                    all_results.extend(data)
                    logger.info(f"{ex}: {len(data)} symbols collected")
            except Exception as e:
                logger.error(f"{ex}: error {e}")

    # ==== Запис у CSV ====
    timestamp_file = datetime.now().strftime('%Y%m%d_%H%M%S')
    folder = 'funding_results'
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, f'funding_{timestamp_file}.csv')

    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['exchange','symbol','funding_rate','next_funding_utc','countdown_sec','funding_timestamp_utc']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_results:
            writer.writerow(row)

    duration = time.time() - start_time
    logger.info(f"Funding collection finished. Duration: {duration:.2f} s, total symbols collected: {len(all_results)}")
    # ==== Видалення PID файлу ====
    os.remove(PID_FILE)

if __name__ == "__main__":
    main()
