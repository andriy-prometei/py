import requests
import time
from typing import Dict, Any, List
import decimal
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MexcScreener:
    BASE_URL = "https://contract.mexc.com/"
    FUNDING_RATE_ENDPOINT = "api/v1/contract/funding_rate/{symbol}"
    CONTRACT_DETAILS_ENDPOINT = "api/v1/contract/detail"

    def __init__(self):
        self.name = "Mexc"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[Mexc] Loaded {len(self.contracts)} contracts")

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
                    raise
                time.sleep(0.5)
        raise RuntimeError("Request failed after retries")

    def get_all_contracts(self) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}{self.CONTRACT_DETAILS_ENDPOINT}"
        try:
            data = self.safe_get(url)
            contracts = []
            for contract in data.get("data", []):
                contracts.append({
                    "symbol": contract["symbol"],
                    "makerFeeRate": decimal.Decimal(contract.get("makerFeeRate", "0")),
                    "takerFeeRate": decimal.Decimal(contract.get("takerFeeRate", "0")),
                })
            return contracts
        except Exception as e:
            logger.error(f"[Mexc] Failed to fetch contracts: {e}")
            return []

    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{self.FUNDING_RATE_ENDPOINT.format(symbol=symbol)}"
        try:
            data = self.safe_get(url).get("data", {})
            funding_rate = decimal.Decimal(data.get("fundingRate", "0")).quantize(decimal.Decimal("1E-6"))
            next_funding_ts = int(data.get("fundingTime", 0)) / 1000  # timestamp in ms
            next_funding_dt = datetime.fromtimestamp(next_funding_ts, tz=timezone.utc) if next_funding_ts else None
            countdown_sec = (next_funding_dt - datetime.now(timezone.utc)).total_seconds() if next_funding_dt else 0
            next_funding_iso = next_funding_dt.isoformat() if next_funding_dt else None
            timestamp = datetime.now(timezone.utc).isoformat()

#            logger.info(f"[Mexc] {symbol} funding fetched at {timestamp}, next in {countdown_sec:.0f}s")

            return {
                "ticker": symbol,
                "funding_rate": funding_rate,
                "funding_timestamp_utc": timestamp,
                "next_funding_utc": next_funding_iso,
                "countdown_sec": countdown_sec
            }
        except Exception as e:
            logger.error(f"[Mexc] Failed to fetch funding for {symbol}: {e}")
            return {
                "ticker": symbol,
                "funding_rate": decimal.Decimal("0"),
                "funding_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "next_funding_utc": None,
                "countdown_sec": 0
            }

    def calculate_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]) -> decimal.Decimal:
        fee = contract["makerFeeRate"] + contract["takerFeeRate"]
        return fr - fee

    def analyze(self) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.get_funding_rate, c["symbol"]): c for c in self.contracts}
            for future in as_completed(futures):
                contract = futures[future]
                try:
                    data = future.result()
                    data["potential_profit"] = self.calculate_profit(data["funding_rate"], contract)
                    results.append(data)
                except Exception as e:
                    logger.error(f"[Mexc] Error processing {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            data = self.analyze()
            logger.info(f"[Mexc] Completed. {len(data)} contracts processed.")
            return data
        except Exception as e:
            logger.error(f"[Mexc] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = MexcScreener()
    out = scr.run()
    print(f"Top: {out[:5]}")
