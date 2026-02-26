import requests
import logging
import decimal
from datetime import datetime, timezone
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class KrakenScreener:
    BASE_URL = "https://futures.kraken.com"
    TICKERS_ENDPOINT = "/derivatives/api/v3/tickers"

    def __init__(self):
        self.name = "Kraken"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        logger.info(f"[Kraken] Screener initialized")

    def safe_get(self, url, params=None, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, timeout=5)
                if r.status_code == 429:
                    # rate limiting
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
        return {}

    def fetch_tickers(self) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}{self.TICKERS_ENDPOINT}"
        data = self.safe_get(url)
        # Kraken returns list of ticker dicts
        return data.get("tickers", [])

    def parse_ticker(self, ticker: Dict[str, Any]) -> Dict[str, Any]:
        # fundingRate could be in ticker under 'fundingRate'
        fr = decimal.Decimal(ticker.get("fundingRate", 0)) if ticker.get("fundingRate") else decimal.Decimal("0")
        fr = fr.quantize(decimal.Decimal("1E-6"))

        # next funding timestamp if present
        next_ts = ticker.get("nextFundingRateTime")
        if next_ts:
            # API returns ms
            next_dt = datetime.fromtimestamp(int(next_ts) / 1000, tz=timezone.utc)
            countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()
            next_iso = next_dt.isoformat()
        else:
            next_iso = None
            countdown = 0

        timestamp = datetime.now(timezone.utc).isoformat()

        return {
            "ticker": ticker.get("symbol"),
            "funding_rate": fr,
            "funding_timestamp_utc": timestamp,
            "next_funding_utc": next_iso,
            "countdown_sec": countdown,
        }

    def run(self):
        try:
            tickers = self.fetch_tickers()
            results = []
            for t in tickers:
                data = self.parse_ticker(t)
                # potential_profit placeholder (zero fees for now)
                data["potential_profit"] = data["funding_rate"]
                results.append(data)
            logger.info(f"[Kraken] {len(results)} contracts processed")
            return results
        except Exception as e:
            logger.error(f"[Kraken] ERROR: {e}")
            return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scr = KrakenScreener()
    out = scr.run()
    print(out[:5])
