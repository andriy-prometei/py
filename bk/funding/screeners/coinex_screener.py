import requests
import logging
import decimal
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class CoinexScreener:
    BASE_URL = "https://api.coinex.com/v2/futures/funding-rate"

    def __init__(self):
        self.name = "CoinEx"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.logger = logging.getLogger(self.name)
        logger.info(f"[CoinEx] Initialized screener")

    def safe_get(self, params=None, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(self.BASE_URL, params=params, timeout=7)
                if r.status_code == 429:
                    logger.warning("[CoinEx] Rate limited, sleeping...")
                    time.sleep(1)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                time.sleep(0.5)
        return None

    def fetch_funding_rates(self):
        """
        Без параметру market — повертає funding для всіх symbols.
        """
        try:
            data = self.safe_get()
            if not data or "data" not in data:
                return []
            return data["data"]
        except Exception as e:
            logger.error(f"[CoinEx] Fetch failed: {e}")
            return []

    def format_record(self, info):
        try:
            ticker = info.get("market")
            fr = decimal.Decimal(info.get("latest_funding_rate", "0")).quantize(decimal.Decimal("1E-6"))
            next_fr = decimal.Decimal(info.get("next_funding_rate", "0")).quantize(decimal.Decimal("1E-6"))

            latest_ts = info.get("latest_funding_time", 0)
            next_ts = info.get("next_funding_time", 0)

            latest_dt = datetime.fromtimestamp(latest_ts / 1000, tz=timezone.utc)
            next_dt = datetime.fromtimestamp(next_ts / 1000, tz=timezone.utc)

            countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()

            return {
                "ticker": ticker,
                "funding_rate": fr,
                "next_funding_rate": next_fr,
                "funding_timestamp_utc": latest_dt.isoformat(),
                "next_funding_utc": next_dt.isoformat(),
                "countdown_sec": countdown,
            }
        except Exception as e:
            logger.error(f"[CoinEx] Format error: {e}")
            return {
                "ticker": info.get("market"),
                "funding_rate": decimal.Decimal("0"),
                "funding_timestamp_utc": None,
                "next_funding_utc": None,
                "countdown_sec": 0,
            }

    def calculate_profit(self, fr, contract):
        # Якщо маєш maker/taker, можна відняти тут
        return fr

    def run(self):
        logger.info("[CoinEx] Running...")
        infos = self.fetch_funding_rates()
        out = []
        for info in infos:
            rec = self.format_record(info)
            rec["potential_profit"] = self.calculate_profit(rec["funding_rate"], rec)
            out.append(rec)

        out.sort(key=lambda x: x["potential_profit"], reverse=True)
        logger.info(f"[CoinEx] Completed, found {len(out)} entries")
        return out

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    screener = CoinexScreener()
    print(screener.run())
