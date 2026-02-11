import requests
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class CoinbaseScreener:
    BASE_URL = "https://api.international.coinbase.com"
    INSTRUMENTS_ENDPOINT = "/api/v1/instruments"
    QUOTE_ENDPOINT = "/api/v1/instruments/{instrument}/quote"

    def __init__(self):
        self.name = "Coinbase"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Funding-Screener",
        })
        self.contracts = self.get_all_contracts()
        logger.info(f"[Coinbase] Loaded {len(self.contracts)} perp instruments")

    def safe_get(self, url: str, params: Dict[str, Any] = None, retries: int = 3):
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
        url = f"{self.BASE_URL}{self.INSTRUMENTS_ENDPOINT}"
        try:
            data = self.safe_get(url)
            contracts = []
            for inst in data:
                if inst.get("type") == "PERP":
                    contracts.append({
                        "symbol": inst.get("symbol"),
                        "instrument_id": inst.get("instrument_id"),
                        "makerFeeRate": decimal.Decimal(inst.get("maker_fee_rate", "0")),
                        "takerFeeRate": decimal.Decimal(inst.get("taker_fee_rate", "0")),
                    })
            return contracts
        except Exception as e:
            logger.error(f"[Coinbase] Failed to fetch instruments: {e}")
            return []

    def get_quote_funding(self, instrument_id: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{self.QUOTE_ENDPOINT.format(instrument=instrument_id)}"
        try:
            data = self.safe_get(url)
            fr = decimal.Decimal(data.get("predicted_funding", "0")).quantize(decimal.Decimal("1E-6"))
            timestamp = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logger.error(f"[Coinbase] Funding quote failed for {instrument_id}: {e}")
            fr = decimal.Decimal("0")
            timestamp = datetime.now(timezone.utc).isoformat()

        logger.info(f"[Coinbase] {instrument_id} predicted funding {fr} @ {timestamp}")

        return {
            "funding_rate": fr,
            "funding_timestamp_utc": timestamp,
            "next_funding_utc": None,
            "countdown_sec": 0
        }

    def calculate_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]) -> decimal.Decimal:
        fee = contract.get("makerFeeRate", decimal.Decimal("0")) + contract.get("takerFeeRate", decimal.Decimal("0"))
        return fr - fee

    def analyze(self) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self.get_quote_funding, c["instrument_id"]): c
                for c in self.contracts
            }
            for future in as_completed(futures):
                contract = futures[future]
                try:
                    data = future.result()
                    data["ticker"] = contract["symbol"]
                    data["potential_profit"] = self.calculate_profit(data["funding_rate"], contract)
                    results.append(data)
                except Exception as e:
                    logger.error(f"[Coinbase] Error for {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self) -> List[Dict[str, Any]]:
        try:
            out = self.analyze()
            logger.info(f"[Coinbase] Completed {len(out)} results")
            return out
        except Exception as e:
            logger.error(f"[Coinbase] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = CoinbaseScreener()
    print(scr.run())
