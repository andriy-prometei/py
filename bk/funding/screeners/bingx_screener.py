import requests
import decimal
import logging
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class BingxScreener:
    BASE_URL = "https://open-api.bingx.com"
    CONTRACTS_ENDPOINT = "/openApi/swap/v2/quote/contracts"
    FUNDING_ENDPOINT = "/openApi/swap/v2/quote/fundingRate"

    FUNDING_INTERVAL = timedelta(hours=8)

    def __init__(self):
        self.name = "BingX"
        self.contracts = self._load_active_contracts()
        logger.info(f"[{self.name}] loaded {len(self.contracts)} active contracts")

    def _load_active_contracts(self):
        url = self.BASE_URL + self.CONTRACTS_ENDPOINT
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        if "data" not in data:
            raise RuntimeError("No data field in contracts response")

        symbols = []
        for c in data["data"]:
            if c.get("status") == 1 and c.get("symbol"):
                symbols.append(c["symbol"])

        if not symbols:
            raise RuntimeError("No active BingX symbols received")

        return symbols

    def _fetch_funding(self, symbol):
        url = self.BASE_URL + self.FUNDING_ENDPOINT
        r = requests.get(url, params={"symbol": symbol}, timeout=10)
        r.raise_for_status()
        data = r.json()

        if "data" not in data or not data["data"]:
            raise RuntimeError(f"No funding data for {symbol}")

        d = data["data"][0]

        funding_rate = decimal.Decimal(d["fundingRate"])
        funding_time = datetime.fromtimestamp(
            int(d["fundingTime"]) / 1000,
            tz=timezone.utc
        )

        next_funding_time = funding_time + self.FUNDING_INTERVAL
        countdown_sec = int((next_funding_time - datetime.now(timezone.utc)).total_seconds())

        return {
            "ticker": symbol,
            "funding_rate": funding_rate,
            "funding_time_utc": funding_time.isoformat(),
            "next_funding_utc": next_funding_time.isoformat(),
            "countdown_sec": countdown_sec
        }

    def run(self):
        results = []

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(self._fetch_funding, s) for s in self.contracts]

            for f in as_completed(futures):
                res = f.result()  # 🔥 якщо помилка — screener падає
                results.append(res)

        return results


if __name__ == "__main__":
    s = BingxScreener()
    data = s.run()
    print(f"OK: {len(data)} contracts")
    for x in data[:10]:
        print(x)
