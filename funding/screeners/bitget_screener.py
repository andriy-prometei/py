import requests
import time
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class BitgetScreener:
    BASE_URL = "https://api.bitget.com"
    CONTRACTS_ENDPOINT = "/api/v2/mix/market/contracts"
    FUNDING_RATE_ENDPOINT = "/api/v2/mix/market/current-fund-rate"
    NEXT_FUNDING_ENDPOINT = "/api/v2/mix/market/funding-time"

    def __init__(self):
        self.name = "Bitget"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[Bitget] Loaded {len(self.contracts)} contracts")

    # ---------- Safe GET with retries ----------
    def safe_get(self, url, params=None, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, timeout=6)
                if r.status_code == 429:
                    time.sleep(0.3)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                time.sleep(0.3)
        raise RuntimeError("Request failed after retries")

    # ---------- Fetch contracts ----------
    def get_all_contracts(self) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}{self.CONTRACTS_ENDPOINT}"
        params = {"productType": "USDT-FUTURES"}

        try:
            data = self.safe_get(url, params=params)
            items = data.get("data", [])
            if not isinstance(items, list):
                logger.error("[Bitget] Unexpected contracts format")
                return []

            contracts = []
            for c in items:
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
            logger.error(f"[Bitget] Failed to fetch contracts: {e}")
            return []

    # ---------- Funding rate ----------
    def get_current_funding(self, symbol: str) -> decimal.Decimal:
        url = f"{self.BASE_URL}{self.FUNDING_RATE_ENDPOINT}"
        params = {"productType": "USDT-FUTURES", "symbol": symbol}

        try:
            data = self.safe_get(url, params=params)
            items = data.get("data", [])

            # Must be list
            if not isinstance(items, list):
                logger.warning(f"[Bitget] Bad funding format for {symbol}")
                return decimal.Decimal("0")

            if len(items) == 0:
                logger.warning(f"[Bitget] EMPTY funding for {symbol}")
                return decimal.Decimal("0")

            row = items[0]
            if not isinstance(row, dict):
                logger.warning(f"[Bitget] Wrong funding type for {symbol}")
                return decimal.Decimal("0")

            fr = row.get("fundingRate", "0")
            return decimal.Decimal(fr).quantize(decimal.Decimal("1E-6"))

        except Exception as e:
            logger.error(f"[Bitget] Funding fetch failed for {symbol}: {e}")
            return decimal.Decimal("0")

    # ---------- Next funding ----------
    def get_next_funding(self, symbol: str):
        url = f"{self.BASE_URL}{self.NEXT_FUNDING_ENDPOINT}"
        params = {"productType": "USDT-FUTURES", "symbol": symbol}

        try:
            data = self.safe_get(url, params=params)
            ft = data.get("data", {})

            if not isinstance(ft, dict):
                return None, 0

            next_ms = int(ft.get("fundingTime", 0))
            if next_ms <= 0:
                return None, 0

            next_dt = datetime.fromtimestamp(next_ms / 1000, tz=timezone.utc)
            countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()

            return next_dt.isoformat(), countdown

        except Exception as e:
            logger.error(f"[Bitget] Next funding failed for {symbol}: {e}")
            return None, 0

    # ---------- Combined fetch ----------
    def get_funding_data(self, symbol: str) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            fr = self.get_current_funding(symbol)
            next_f, countdown = self.get_next_funding(symbol)

            logger.info(f"[Bitget] {symbol} FR={fr}, next={countdown:.0f}s")

            return {
                "ticker": symbol,
                "funding_rate": fr,
                "funding_timestamp_utc": timestamp,
                "next_funding_utc": next_f,
                "countdown_sec": countdown,
            }

        except Exception as e:
            logger.error(f"[Bitget] FULL FAIL {symbol}: {e}")
            return {
                "ticker": symbol,
                "funding_rate": decimal.Decimal("0"),
                "funding_timestamp_utc": timestamp,
                "next_funding_utc": None,
                "countdown_sec": 0,
            }

    # ---------- Profit calc ----------
    def calc_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]):
        return fr - (contract["makerFeeRate"] + contract["takerFeeRate"])

    # ---------- Run analysis ----------
    def analyze(self) -> List[Dict[str, Any]]:
        results = []

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(self.get_funding_data, c["symbol"]): c for c in self.contracts}

            for fut in as_completed(futures):
                contract = futures[fut]
                try:
                    row = fut.result()
                    row["potential_profit"] = self.calc_profit(row["funding_rate"], contract)
                    results.append(row)
                except Exception as e:
                    logger.error(f"[Bitget] Error in {contract['symbol']}: {e}")

        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            res = self.analyze()
            logger.info(f"[Bitget] Completed with {len(res)} rows")
            return res
        except Exception as e:
            logger.error(f"[Bitget] GLOBAL FAILURE: {e}")
            return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s = BitgetScreener()
    print(s.run())
