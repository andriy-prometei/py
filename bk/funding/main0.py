import os
import csv
import importlib
import logging
import inspect
import pkgutil
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import psutil  # pip install psutil

LOCK_FILE = "main0.lock"
LOG_FILE = "main0.log"

# ------------------ Setup logging ------------------
logger = logging.getLogger("ScreenerManager")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Console handler
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# File handler
fh = logging.FileHandler(LOG_FILE)
fh.setFormatter(formatter)
logger.addHandler(fh)

# run 1 instance silultaneously
def check_already_running():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read())
                # Перевіряємо, чи процес існує
                if psutil.pid_exists(pid):
                    logger.info(f"main0.py вже запущений! PID={pid}")
                    sys.exit(0)
                else:
                    logger.info("Старий lock знайдено, але процес не живий. Перезаписуємо.")
        except Exception as e:
            logger.info(f"Помилка при читанні lock-файлу: {e}")
            
    # Створюємо новий lock
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def remove_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

# ---------------------- Dynamic Loader ----------------------
def load_screeners():
    """Динамічне завантаження всіх класів зі screeners/, які закінчуються на 'Screener'"""
    import screeners

    screeners_list = []
    pkg_path = screeners.__path__

    for module_info in pkgutil.iter_modules(pkg_path):
        module_name = module_info.name
        try:
            module = importlib.import_module(f"screeners.{module_name}")
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if name.endswith("Screener"):
                    try:
                        screeners_list.append(obj())
                        logger.info(f"Loaded screener: {name}")
                    except Exception as e:
                        logger.error(f"Failed to init {name}: {e}")
        except Exception as e:
            logger.error(f"Failed to import module {module_name}: {e}")

    return screeners_list

# ---------------------- Manager ----------------------
class ScreenerManager:
    def __init__(self):
        self.screeners = load_screeners()

    def run_one(self, screener):
        """Запуск одного скрінера з обробкою помилок"""
        try:
            data = screener.run()
#            data = data[:2] + data[-2:] if len(data) > 4 else data
            return {"ex_name": screener.name, "coins": data}
        except Exception as e:
            logger.error(f"Screener {screener.name} failed: {e}")
            return {"ex_name": screener.name, "coins": []}

    def run_screeners_parallel(self):
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self.run_one, s): s for s in self.screeners}
            for future in as_completed(futures):
                res = future.result()
                results.append(res)
        return results

    def save_to_csv(self, all_results):
        os.makedirs("results", exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"results/{ts}.csv"

        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "exchange", "ticker", "funding_rate", "potential_profit",
                "funding_timestamp_utc", "next_funding_utc", "countdown_sec"
            ])

            for exchange in all_results:
                for coin in exchange["coins"]:
                    writer.writerow([
                        exchange["ex_name"],
                        coin.get("ticker"),
                        coin.get("funding_rate"),
                        coin.get("potential_profit"),
                        coin.get("funding_timestamp_utc"),
                        coin.get("next_funding_utc"),
                        coin.get("countdown_sec"),
                    ])
#                    logger.info(f"{coin.get('ticker')}. Funding: {coin.get('funding_rate')}, "
#                                f"Profit: {coin.get('potential_profit',0):.6%}, "
#                                f"Next in {coin.get('countdown_sec',0):.0f}s at {coin.get('next_funding_utc')}")

        logger.info(f"Saved results → {filename}")

    def run(self):
        results = self.run_screeners_parallel()
        self.save_to_csv(results)
        return results

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    import atexit
    atexit.register(remove_lock)  # Гарантовано видалимо lock при завершенні
    check_already_running()

    manager = ScreenerManager()
    manager.run()
