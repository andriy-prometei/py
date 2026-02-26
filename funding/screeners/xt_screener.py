import requests
import time
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class XTScreener:
    BASE_URL = "https://fapi.xt.com"  # публічний XT futures API
    CONTRACTS_ENDPOINT = "/future/market/v1/public/cg/contracts"
    FUNDING_RECORDS_ENDPOINT = "/future/market/v1/public/q/funding-rate-record"

    def __init__(self):
        self.name = "XT"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[XT] Loaded {len(self.contracts)} perpetual contracts")

    def safe_get(self, url, params=None, retries=3):
        """GET із retry та timeout."""
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
        """Завантажує список contract із funding rates із XT.""" 
        url = f"{self.BASE_URL}{self.CONTRACTS_ENDPOINT}"
        try:
            data = self.safe_get(url)
            contracts = []
            for item in data:
                # беремо тільки perpetual
                if item.get("product_type", "").upper() == "PERPETUAL":
                    contracts.append({
                        "symbol": item.get("symbol"),
                        "makerFeeRate": decimal.Decimal("0"),  # XT API публічних maker/taker не дає
                        "takerFeeRate": decimal.Decimal("0"),
                        "currentFundingRate": decimal.Decimal(item.get("funding_rate", "0")).quantize(
                            decimal.Decimal("1E-6")),
                        "nextFundingRate": decimal.Decimal(item.get("next_funding_rate", "0")).quantize(
                            decimal.Decimal("1E-6")),
                        "nextFundingTime": item.get("next_funding_rate_timestamp")
                    })
            return contracts
        except Exception as e:
            logger.error(f"[XT] Failed to fetch contracts: {e}")
            return []

    def get_funding_data(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Формує funding data для одного контракту."""
        try:
            sym = contract["symbol"]
            # funding rate вже у CONTRACTS_ENDPOINT
            fr = contract["currentFundingRate"]
            next_ts_ms = contract.get("nextFundingTime") or 0
            next_dt = datetime.fromtimestamp(next_ts_ms / 1000, tz=timezone.utc) \
                if next_ts_ms else None
            countdown = (next_dt - datetime.now(timezone.utc)).total_seconds() if next_dt else 0

            timestamp = datetime.now(timezone.utc).isoformat()
            logger.info(f"[XT] {sym} funding fetched at {timestamp}, next in {countdown:.0f}s")

            return {
                "ticker": sym,
                "funding_rate": fr,
                "funding_timestamp_utc": timestamp,
                "next_funding_utc": next_dt.isoformat() if next_dt else None,
                "countdown_sec": countdown
            }
        except Exception as e:
            logger.error(f"[XT] Failed funding for {contract.get('symbol')}: {e}")
            return {
                "ticker": contract.get("symbol"),
                "funding_rate": decimal.Decimal("0"),
                "funding_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "next_funding_utc": None,
                "countdown_sec": 0
            }

    def calculate_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]) -> decimal.Decimal:
        """Обчислення потенційного прибутку."""
        # без maker/taker fee, але можна додати, якщо знаєш їх
        return fr

    def analyze(self) -> List[Dict[str, Any]]:
        """Аналіз funding rates."""
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
                    logger.error(f"[XT] Error processing {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            results = self.analyze()
            logger.info(f"[XT] Completed. {len(results)} symbols processed.")
            return results
        except Exception as e:
            logger.error(f"[XT] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = XTScreener()
    print(scr.run())
