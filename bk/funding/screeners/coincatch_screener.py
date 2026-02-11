import requests
import decimal
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class CoincatchScreener:
    BASE_URL = "https://api.coincatch.com"
    TICKERS_ENDPOINT = "/api/mix/v1/market/tickers"

    def __init__(self):
        self.name = "CoinCatch"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        logger.info(f"[CoinCatch] Initialized")

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

    def fetch_funding_data(self) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}{self.TICKERS_ENDPOINT}"
        params = {"productType": "umcbl"}  # perpetual
        try:
            response = self.safe_get(url, params=params)
            data = response.get("data", [])
        except Exception as e:
            logger.error(f"[CoinCatch] Funding fetch failed: {e}")
            return []

        results = []
        for item in data:
            symbol = item.get("symbol")
            fr_raw = item.get("fundingRate", "0")
            try:
                funding_rate = decimal.Decimal(fr_raw).quantize(decimal.Decimal("1E-6"))
            except Exception:
                funding_rate = decimal.Decimal("0")

            timestamp_ms = item.get("timestamp")
            if timestamp_ms:
                try:
                    ts = int(timestamp_ms) / 1000
                    funding_timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                except Exception:
                    funding_timestamp = datetime.now(timezone.utc).isoformat()
            else:
                funding_timestamp = datetime.now(timezone.utc).isoformat()

            results.append({
                "ticker": symbol,
                "funding_rate": funding_rate,
                "funding_timestamp_utc": funding_timestamp,
                "next_funding_utc": None,
                "countdown_sec": 0
            })

        return results

    def calculate_profit(self, fr: decimal.Decimal) -> decimal.Decimal:
        # Якщо немає maker/taker fee API — припустимо 0
        return fr

    def run(self):
        try:
            data = self.fetch_funding_data()
            for item in data:
                item["potential_profit"] = self.calculate_profit(item["funding_rate"])
            logger.info(f"[CoinCatch] Retrieved {len(data)} symbols")
            return data
        except Exception as e:
            logger.error(f"[CoinCatch] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scr = CoincatchScreener()
    print(scr.run())
