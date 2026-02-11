import requests
import time
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class BitMartScreener:
    BASE_URL = "https://api-cloud-v2.bitmart.com"
    FUNDING_RATE_ENDPOINT = "/contract/public/funding-rate"
    INSTRUMENTS_ENDPOINT = "/contract/public/details"

    def __init__(self):
        self.name = "BitMart"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[BitMart] Loaded {len(self.contracts)} contracts")

    def safe_get(self, url, params=None, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, timeout=5)
                if r.status_code == 429:
                    time.sleep(1)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    logger.warning(f"[BitMart] Request failed for {url} after {retries} retries: {e}")
                    return None
                time.sleep(0.5)
        return None

    def get_all_contracts(self) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}{self.INSTRUMENTS_ENDPOINT}"
        data = self.safe_get(url)
        contracts = []
        if not data:
            logger.warning("[BitMart] No contract data received")
            return contracts
        symbols_data = data.get("data", {}).get("symbols", [])
        for c in symbols_data:
            if c.get("status") == "Trading":
                contracts.append({
                    "symbol": c["symbol"],
                    "makerFeeRate": decimal.Decimal(c.get("makerFeeRate", "0")),
                    "takerFeeRate": decimal.Decimal(c.get("takerFeeRate", "0")),
                })
        return contracts

    def get_funding_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        url = f"{self.BASE_URL}{self.FUNDING_RATE_ENDPOINT}"
        params = {"symbol": symbol}
        data = self.safe_get(url, params=params)
        if not data or not data.get("data"):
            logger.info(f"[BitMart] No funding data for {symbol}, skipping")
            return None

        info = data.get("data", {})
        raw_rate = info.get("expected_rate") or info.get("rate_value") or "0"
        if decimal.Decimal(raw_rate) == 0:
            # пропускаємо контракти без funding
            logger.info(f"[BitMart] Funding rate 0 for {symbol}, skipping")
            return None

        funding_rate = decimal.Decimal(raw_rate).quantize(decimal.Decimal("1E-6"))
        next_ms = int(info.get("funding_time", 0))
        next_dt = datetime.fromtimestamp(next_ms / 1000, tz=timezone.utc)
        countdown_sec = max((next_dt - datetime.now(timezone.utc)).total_seconds(), 0)
        timestamp = datetime.now(timezone.utc).isoformat()

        logger.info(f"[BitMart] {symbol} funding fetched at {timestamp}, next at {next_dt.isoformat()}")

        return {
            "ticker": symbol,
            "funding_rate": funding_rate,
            "funding_timestamp_utc": timestamp,
            "next_funding_utc": next_dt.isoformat(),
            "countdown_sec": countdown_sec
        }

    def calculate_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]) -> decimal.Decimal:
        fee = contract["makerFeeRate"] + contract["takerFeeRate"]
        return fr - fee

    def analyze(self) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.get_funding_data, c["symbol"]): c for c in self.contracts}
            for future in as_completed(futures):
                contract = futures[future]
                try:
                    data = future.result()
                    if data is None:
                        continue  # пропускаємо контракти без funding
                    data["potential_profit"] = self.calculate_profit(data["funding_rate"], contract)
                    results.append(data)
                except Exception as e:
                    logger.warning(f"[BitMart] Error for {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            res = self.analyze()
            logger.info(f"[BitMart] Completed: {len(res)} contracts processed.")
            return res
        except Exception as e:
            logger.warning(f"[BitMart] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = BitMartScreener()
    print(scr.run())
