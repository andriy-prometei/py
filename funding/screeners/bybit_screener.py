import requests
import time
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class BybitScreener:
    BASE_URL = "https://api.bybit.com"
    FUNDING_HISTORY_ENDPOINT = "/v5/market/funding/history"
    TICKERS_ENDPOINT = "/v5/market/tickers"
    INSTRUMENTS_INFO_ENDPOINT = "/v5/market/instruments-info"

    def __init__(self):
        self.name = "Bybit"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[Bybit] Loaded {len(self.contracts)} contracts")

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
        url = f"{self.BASE_URL}{self.INSTRUMENTS_INFO_ENDPOINT}"
        params = {"category": "linear"}
        try:
            data = self.safe_get(url, params=params)
            contracts = []
            for c in data.get("result", {}).get("list", []):
                contracts.append({
                    "symbol": c["symbol"],
                    "makerFeeRate": decimal.Decimal(c.get("makerFee", "0")),
                    "takerFeeRate": decimal.Decimal(c.get("takerFee", "0")),
                })
            return contracts
        except Exception as e:
            logger.error(f"[Bybit] Failed to fetch contracts: {e}")
            return []

    def get_latest_funding(self, symbol: str) -> decimal.Decimal:
        url = f"{self.BASE_URL}{self.FUNDING_HISTORY_ENDPOINT}"
        params = {"category": "linear", "symbol": symbol, "limit": 1}
        data = self.safe_get(url, params=params)
        try:
            item = data.get("result", {}).get("list", [])[0]
            return decimal.Decimal(item.get("fundingRate", "0")).quantize(decimal.Decimal("1E-6"))
        except Exception:
            return decimal.Decimal("0")

    def get_next_funding_info(self, symbol: str):
        url = f"{self.BASE_URL}{self.TICKERS_ENDPOINT}"
        params = {"category": "linear", "symbol": symbol}
        data = self.safe_get(url, params=params)
        try:
            info = data.get("result", {}).get("list", [])[0]
            fr = decimal.Decimal(info.get("fundingRate", "0")).quantize(decimal.Decimal("1E-6"))
            next_ts = int(info.get("nextFundingTime", 0)) / 1000
            next_dt = datetime.fromtimestamp(next_ts, tz=timezone.utc)
            countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()
            return fr, next_dt.isoformat(), countdown
        except Exception:
            return decimal.Decimal("0"), None, 0

    def get_funding_data(self, symbol: str) -> Dict[str, Any]:
        latest_fr = self.get_latest_funding(symbol)
        current_fr, next_utc, countdown = self.get_next_funding_info(symbol)
        timestamp = datetime.now(timezone.utc).isoformat()
        return {
            "ticker": symbol,
            "funding_rate": current_fr if current_fr != 0 else latest_fr,
            "funding_timestamp_utc": timestamp,
            "next_funding_utc": next_utc,
            "countdown_sec": countdown,
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
                    data["potential_profit"] = self.calculate_profit(data["funding_rate"], contract)
                    results.append(data)
                except Exception as e:
                    logger.error(f"[Bybit] Error for {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            results = self.analyze()
            logger.info(f"[Bybit] Completed: {len(results)}")
            return results
        except Exception as e:
            logger.error(f"[Bybit] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = BybitScreener()
    print(scr.run())
