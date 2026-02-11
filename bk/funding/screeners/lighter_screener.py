import requests
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
import decimal

logger = logging.getLogger(__name__)

class LighterScreener:
    BASE_URL = "https://mainnet.zklighter.elliot.ai"
    FUNDING_RATES_ENDPOINT = "/api/v1/funding-rates"

    def __init__(self):
        self.name = "Lighter"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        logger.info(f"[Lighter] Screener initialized")

    def safe_get(self, url, params=None, retries=3):
        """Simple GET with retries and timeout."""
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, timeout=5)
                if r.status_code == 429:
                    # Rate limit — sleep and retry
                    time.sleep(1)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                time.sleep(0.5)
        raise RuntimeError("Request failed after retries")

    def run(self) -> List[Dict[str, Any]]:
        """Fetch funding rates from Lighter API."""
        url = f"{self.BASE_URL}{self.FUNDING_RATES_ENDPOINT}"
        try:
            data = self.safe_get(url)
        except Exception as e:
            logger.error(f"[Lighter] API error: {e}")
            return []

        results = []
        timestamp = datetime.now(timezone.utc).isoformat()

        # Funding rates are expected in a list under top‑level response
        entries = data.get("fundingRates") or data.get("data") or []
        for entry in entries:
            try:
                symbol = entry.get("symbol")
                # funding rate returned as string or number
                fr_raw = entry.get("fundingRate") or entry.get("rate") or 0
                funding_rate = decimal.Decimal(str(fr_raw)).quantize(decimal.Decimal("1E-8"))

                # Next funding: Lighter uses hourly funding — next = now + remaining to hour
                now_utc = datetime.now(timezone.utc)
                next_hour = (now_utc.replace(minute=0, second=0, microsecond=0) 
                             + timedelta(hours=1))
                countdown_sec = (next_hour - now_utc).total_seconds()
                next_funding_utc = next_hour.isoformat()

                results.append({
                    "ticker": symbol,
                    "funding_rate": funding_rate,
                    "funding_timestamp_utc": timestamp,
                    "next_funding_utc": next_funding_utc,
                    "countdown_sec": countdown_sec
                })
                logger.info(f"[Lighter] {symbol}: rate={funding_rate}, next in {countdown_sec:.0f}s")
            except Exception as e:
                logger.error(f"[Lighter] parsing error for entry: {e}")

        return results

if __name__ == "__main__":
    import logging, time
    logging.basicConfig(level=logging.INFO)
    scr = LighterScreener()
    out = scr.run()
    print(out[:10])
