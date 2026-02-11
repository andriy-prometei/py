import requests
import time
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class PoloniexScreener:
    BASE_URL = "https://futures-api.poloniex.com"

    CONTRACTS_ENDPOINT = "/api/v1/contracts/active"
    FUNDING_CURRENT_ENDPOINT = "/api/v1/funding-rate/{}/current"

    def __init__(self):
        self.name = "Poloniex"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[Poloniex] Loaded {len(self.contracts)} perpetual contracts")

    # ---------------- helpers ----------------
    def safe_get(self, url, retries=3):
        for i in range(retries):
            try:
                r = self.session.get(url, timeout=5)
                if r.status_code == 429:
                    time.sleep(1)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception:
                if i == retries - 1:
                    raise
                time.sleep(0.5)
        raise RuntimeError("request failed")

    # ---------------- contracts ----------------
    def get_all_contracts(self) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}{self.CONTRACTS_ENDPOINT}"
        data = self.safe_get(url)

        contracts = []
        for c in data.get("data", []):
            if c.get("status") != "Open":
                continue
            if c.get("type") != "FFWCSX":   # perpetual
                continue

            contracts.append({
                "symbol": c["symbol"],
                "makerFeeRate": decimal.Decimal(str(c.get("makerFeeRate", 0))),
                "takerFeeRate": decimal.Decimal(str(c.get("takerFeeRate", 0))),
            })
        return contracts

    # ---------------- funding ----------------
    def get_funding_data(self, symbol: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{self.FUNDING_CURRENT_ENDPOINT.format(symbol)}"
        data = self.safe_get(url)

        try:
            d = data["data"]
            fr = decimal.Decimal(d["fundingRate"]).quantize(decimal.Decimal("1E-6"))
            next_ts = int(d["nextFundingRateTime"]) / 1000
            next_dt = datetime.fromtimestamp(next_ts, tz=timezone.utc)
            countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()
        except Exception:
            fr = decimal.Decimal("0")
            next_dt = None
            countdown = 0

        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[Poloniex] {symbol} funding {fr}, next in {countdown:.0f}s")

        return {
            "ticker": symbol,
            "funding_rate": fr,
            "funding_timestamp_utc": ts,
            "next_funding_utc": next_dt.isoformat() if next_dt else None,
            "countdown_sec": countdown,
        }

    # ---------------- profit ----------------
    def calculate_profit(self, fr: decimal.Decimal, c: Dict[str, Any]) -> decimal.Decimal:
        return fr - (c["makerFeeRate"] + c["takerFeeRate"])

    # ---------------- analyze ----------------
    def analyze(self) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.get_funding_data, c["symbol"]): c for c in self.contracts}

            for future in as_completed(futures):
                c = futures[future]
                try:
                    d = future.result()
                    d["potential_profit"] = self.calculate_profit(d["funding_rate"], c)
                    results.append(d)
                except Exception as e:
                    logger.error(f"[Poloniex] {c['symbol']} failed: {e}")

        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    # ---------------- run ----------------
    def run(self):
        try:
            res = self.analyze()
            logger.info(f"[Poloniex] Completed: {len(res)} contracts")
            return res
        except Exception as e:
            logger.error(f"[Poloniex] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s = PoloniexScreener()
    print(s.run()[:5])
