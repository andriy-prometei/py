import requests
import logging
import decimal
import time
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class BtseScreener:
    BASE_URL = "https://api.btse.com/futures"
    FUNDING_HISTORY_ENDPOINT = "/api/v2.3/funding_history"
    INSTRUMENTS_ENDPOINT = "/api/v2.3/instruments-info"

    def __init__(self):
        self.name = "BTSE"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_contracts()
        logger.info(f"[BTSE] Loaded {len(self.contracts)} perpetual futures")

    def safe_get(self, url, params=None, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, timeout=8)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    logger.error(f"[BTSE] GET failed {url} params {params}: {e}")
                    return None
                time.sleep(0.5)
        return None

    def get_contracts(self) -> List[Dict[str, Any]]:
        """ Отримуємо список перпетуал контрактів з instruments-info (працює без auth) """
        url = f"{self.BASE_URL}{self.INSTRUMENTS_ENDPOINT}"
        data = self.safe_get(url)
        contracts = []
        if not data:
            return contracts

        for c in data.get("result", []):
            sym = c.get("symbol")
            # Перпетуали на BTSE мають “-PERP”
            if sym and sym.endswith("-PERP"):
                contracts.append({
                    "symbol": sym,
                    "makerFeeRate": decimal.Decimal(c.get("makerFee", "0")),
                    "takerFeeRate": decimal.Decimal(c.get("takerFee", "0"))
                })
        return contracts

    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """ Отримуємо останній funding rate через funding_history """
        url = f"{self.BASE_URL}{self.FUNDING_HISTORY_ENDPOINT}"
        params = {"symbol": symbol, "count": 1}
        data = self.safe_get(url, params=params)

        fr = decimal.Decimal("0")
        last_ts = None

        if data and isinstance(data, dict) and symbol in data:
            hist = data[symbol]
            if hist and len(hist) > 0:
                item = hist[0]
                try:
                    fr = decimal.Decimal(str(item.get("rate", "0"))).quantize(decimal.Decimal("1E-6"))
                    last_ts = int(item.get("time", 0))
                except Exception as e:
                    logger.error(f"[BTSE] parse funding for {symbol} failed: {e}")

        if last_ts:
            funding_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
            funding_iso = funding_dt.isoformat()
            next_dt = funding_dt + timedelta(hours=8)
            countdown_sec = (next_dt - datetime.now(timezone.utc)).total_seconds()
            next_iso = next_dt.isoformat()
        else:
            funding_iso = datetime.now(timezone.utc).isoformat()
            next_iso = None
            countdown_sec = 0

        logger.info(f"[BTSE] {symbol} funding={fr} next in {countdown_sec:.0f}s")

        return {
            "ticker": symbol,
            "funding_rate": fr,
            "funding_timestamp_utc": funding_iso,
            "next_funding_utc": next_iso,
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
                    data["potential_profit"] = self.calculate_profit(data["funding_rate"], contract)
                    results.append(data)
                except Exception as e:
                    logger.error(f"[BTSE] analysis error {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            return self.analyze()
        except Exception as e:
            logger.error(f"[BTSE] run error: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = BtseScreener()
    print(scr.run())
