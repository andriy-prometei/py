import requests
import time
from typing import Dict, Any, List
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class BinanceScreener:
    BASE_URL = "https://fapi.binance.com"
    EXCHANGE_INFO_ENDPOINT = "/fapi/v1/exchangeInfo"
    FUNDING_RATE_ENDPOINT = "/fapi/v1/premiumIndex"

    def __init__(self):
        self.name = "Binance"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[Binance] Loaded {len(self.contracts)} perpetual futures")

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
        url = f"{self.BASE_URL}{self.EXCHANGE_INFO_ENDPOINT}"
        data = self.safe_get(url)
        contracts = []
        for sym in data.get("symbols", []):
            if sym.get("contractType") != "PERPETUAL":
                continue
            contracts.append({
                "symbol": sym["symbol"],
                "makerFeeRate": decimal.Decimal(sym.get("makerFeeRate", "0")),
                "takerFeeRate": decimal.Decimal(sym.get("takerFeeRate", "0")),
            })
        return contracts

    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{self.FUNDING_RATE_ENDPOINT}"
        data = self.safe_get(url, params={"symbol": symbol})
        try:
            funding_rate = decimal.Decimal(data["lastFundingRate"])
            next_funding_ts = int(data["nextFundingTime"]) / 1000
            next_funding_dt = datetime.fromtimestamp(next_funding_ts, tz=timezone.utc)
            countdown_sec = (next_funding_dt - datetime.now(timezone.utc)).total_seconds()
        except Exception:
            funding_rate = decimal.Decimal("0")
            next_funding_dt = None
            countdown_sec = 0

        funding_rate = funding_rate.quantize(decimal.Decimal("1E-6"))
        timestamp = datetime.now(timezone.utc).isoformat()
#        logger.info(f"[Binance] {symbol} funding fetched at {timestamp}, next in {countdown_sec:.0f}s")

        return {
            "ticker": symbol,
            "funding_rate": funding_rate,
            "funding_timestamp_utc": timestamp,
            "next_funding_utc": next_funding_dt.isoformat() if next_funding_dt else None,
            "countdown_sec": countdown_sec
        }

    def calculate_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]) -> decimal.Decimal:
        fee = contract["makerFeeRate"] + contract["takerFeeRate"]
        return fr - fee

    def analyze(self) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.get_funding_rate, c["symbol"]): c for c in self.contracts}
            for future in as_completed(futures):
                contract = futures[future]
                try:
                    data = future.result()
                    profit = self.calculate_profit(data["funding_rate"], contract)
                    data["potential_profit"] = profit
                    results.append(data)
                except Exception as e:
                    logger.error(f"[Binance] Failed {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            data = self.analyze()
            logger.info(f"[Binance] Completed. {len(data)} symbols processed.")
            return data
        except Exception as e:
            logger.error(f"[Binance] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scr = BinanceScreener()
    out = scr.run()
    print(f"Top: {out[:5]}")
