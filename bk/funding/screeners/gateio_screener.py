import requests
import time
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class GateioScreener:
    BASE_URL = "https://api.gateio.ws/api/v4"
    CONTRACTS_ENDPOINT = "/futures/usdt/contracts"

    def __init__(self):
        self.name = "Gate.io"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[Gate.io] Loaded {len(self.contracts)} contracts")

    def safe_get(self, url, params=None, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, timeout=8)
                if r.status_code == 429:
                    time.sleep(1)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                time.sleep(0.5)
        raise RuntimeError("Gate.io request failed")

    def get_all_contracts(self) -> List[Dict[str, Any]]:
        """Запит усіх USDT perpetual контрактів з funding info."""
        try:
            data = self.safe_get(f"{self.BASE_URL}{self.CONTRACTS_ENDPOINT}")
            contracts = []
            for c in data:
                # Переконатись, що контракт в торгівлі
                if c.get("status") == "trading":
                    contracts.append({
                        "symbol": c["name"],  # наприклад "BTC_USDT"
                        "funding_rate": decimal.Decimal(c.get("funding_rate", "0")),
                        "next_apply_ts": int(c.get("funding_next_apply", 0)),
                        "makerFeeRate": decimal.Decimal(c.get("maker_fee_rate", "0")),
                        "takerFeeRate": decimal.Decimal(c.get("taker_fee_rate", "0")),
                    })
            return contracts
        except Exception as e:
            logger.error(f"[Gate.io] Failed to fetch contracts: {e}")
            return []

    def get_funding_data(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Пакує funding дані з контракту."""
        try:
            symbol = contract["symbol"]
            fr = contract["funding_rate"].quantize(decimal.Decimal("1E-6"))

            # next funding time
            next_ts = contract.get("next_apply_ts", 0)
            if next_ts:
                next_dt = datetime.fromtimestamp(next_ts, tz=timezone.utc)
                countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()
                next_iso = next_dt.isoformat()
            else:
                next_iso = None
                countdown = 0

            timestamp = datetime.now(timezone.utc).isoformat()
            logger.info(f"[Gate.io] {symbol} funding fetched at {timestamp}, next in {countdown:.0f}s")

            return {
                "ticker": symbol,
                "funding_rate": fr,
                "funding_timestamp_utc": timestamp,
                "next_funding_utc": next_iso,
                "countdown_sec": countdown,
            }
        except Exception as e:
            logger.error(f"[Gate.io] Error packaging funding for {contract.get('symbol')}: {e}")
            return {
                "ticker": contract.get("symbol"),
                "funding_rate": decimal.Decimal("0"),
                "funding_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "next_funding_utc": None,
                "countdown_sec": 0,
            }

    def calculate_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]) -> decimal.Decimal:
        fee = contract["makerFeeRate"] + contract["takerFeeRate"]
        return fr - fee

    def analyze(self) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.get_funding_data, c): c for c in self.contracts}
            for future in as_completed(futures):
                contract = futures[future]
                try:
                    data = future.result()
                    data["potential_profit"] = self.calculate_profit(data["funding_rate"], contract)
                    results.append(data)
                except Exception as e:
                    logger.error(f"[Gate.io] Analysis error {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            results = self.analyze()
            logger.info(f"[Gate.io] Completed: {len(results)}")
            return results
        except Exception as e:
            logger.error(f"[Gate.io] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scr = GateioScreener()
    print(scr.run())
