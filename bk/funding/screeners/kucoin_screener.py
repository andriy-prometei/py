import requests
import decimal
import logging
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class KucoinScreener:
    BASE_FUTURES_URL = "https://api-futures.kucoin.com"
    BASE_UNIFIED_URL = "https://api.kucoin.com"
    CONTRACTS_ENDPOINT = "/api/v1/contracts/active"
    FUNDING_RATE_ENDPOINT = "/api/ua/v1/market/funding-rate"

    def __init__(self):
        self.name = "KuCoin"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[KuCoin] Loaded {len(self.contracts)} contracts")

    def safe_get(self, url, params=None, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, timeout=6)
                if r.status_code == 429:
                    time.sleep(1)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                time.sleep(0.5)
        raise RuntimeError("Request failed after retries")

    def get_all_contracts(self) -> List[Dict[str, Any]]:
        try:
            data = self.safe_get(f"{self.BASE_FUTURES_URL}{self.CONTRACTS_ENDPOINT}")
            contracts = []
            for c in data.get("data", []):
                symbol = c.get("symbol")
                if not symbol:
                    continue
                contracts.append({
                    "symbol": symbol,
                    "makerFeeRate": decimal.Decimal(c.get("makerFeeRate", "0")),
                    "takerFeeRate": decimal.Decimal(c.get("takerFeeRate", "0")),
                })
            return contracts
        except Exception as e:
            logger.error(f"[KuCoin] Failed fetching contracts: {e}")
            return []

    def get_funding_data(self, symbol: str) -> Dict[str, Any]:
        params = {"symbol": symbol}
        try:
            data = self.safe_get(f"{self.BASE_UNIFIED_URL}{self.FUNDING_RATE_ENDPOINT}", params=params)
            info = data.get("data", {})
            fr_val = info.get("nextFundingRate", info.get("predictedValue", info.get("value", 0)))
            fr = decimal.Decimal(fr_val).quantize(decimal.Decimal("1E-6"))

            next_ms = info.get("fundingTime")
            if next_ms:
                next_dt = datetime.fromtimestamp(int(next_ms) / 1000, tz=timezone.utc)
                countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()
                next_iso = next_dt.isoformat()
            else:
                next_iso = None
                countdown = 0

            timestamp = datetime.now(timezone.utc).isoformat()
            logger.info(f"[KuCoin] {symbol} funding fetched at {timestamp}, next in {countdown:.0f}s")

            return {
                "ticker": symbol,
                "funding_rate": fr,
                "funding_timestamp_utc": timestamp,
                "next_funding_utc": next_iso,
                "countdown_sec": countdown,
            }
        except Exception as e:
            logger.error(f"[KuCoin] Error fetching funding for {symbol}: {e}")
            return {
                "ticker": symbol,
                "funding_rate": decimal.Decimal("0"),
                "funding_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "next_funding_utc": None,
                "countdown_sec": 0,
            }

    def calculate_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]) -> decimal.Decimal:
        return fr - (contract["makerFeeRate"] + contract["takerFeeRate"])

    def analyze(self) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.get_funding_data, c["symbol"]): c for c in self.contracts}
            for future in as_completed(futures):
                contract = futures[future]
                try:
                    data = future.result()
                    data["potential_profit"] = self.calculate_profit(data["funding_rate"], contract)
                    results.append(data)
                except Exception as e:
                    logger.error(f"[KuCoin] Analyze error {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            out = self.analyze()
            logger.info(f"[KuCoin] Completed. {len(out)} symbols.")
            return out
        except Exception as e:
            logger.error(f"[KuCoin] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = KucoinScreener()
    print(scr.run())
