import requests
import time
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# спробуємо імпортувати certifi
try:
    import certifi
    CERT_FILE = certifi.where()
    CERT_VERIFY = True
except ImportError:
    CERT_FILE = None
    CERT_VERIFY = False
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    logger.warning("certifi not found, SSL verification is disabled!")

class HuobiScreener:
    BASE_URL = "https://api.hbdm.com"
    FUNDING_RATE_ENDPOINT = "/linear-swap-api/v1/swap_funding_rate"
    CONTRACT_INFO_ENDPOINT = "/linear-swap-api/v1/swap_contract_info"

    def __init__(self):
        self.name = "Huobi"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[Huobi] Loaded {len(self.contracts)} contracts")

    def safe_get(self, url, params=None, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(
                    url, params=params, timeout=5,
                    verify=CERT_FILE if CERT_VERIFY else False
                )
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
        """Fetch list of active Huobi USDT perpetual contracts."""
        url = f"{self.BASE_URL}{self.CONTRACT_INFO_ENDPOINT}"
        try:
            data = self.safe_get(url)
            contracts = []
            for c in data.get("data", []):
                if c.get("contract_status") == "1":
                    contracts.append({
                        "symbol": c["contract_code"],
                        "makerFeeRate": decimal.Decimal(c.get("maker_fee_rate", "0")),
                        "takerFeeRate": decimal.Decimal(c.get("taker_fee_rate", "0")),
                    })
            return contracts
        except Exception as e:
            logger.error(f"[Huobi] Failed fetch contracts: {e}")
            return []

    def get_funding_data(self, symbol: str) -> Dict[str, Any]:
        """Get funding_rate + next_funding_time from Huobi."""
        url = f"{self.BASE_URL}{self.FUNDING_RATE_ENDPOINT}"
        try:
            data = self.safe_get(url, params={"contract_code": symbol})
            item = data.get("data", {})
            fr_str = item.get("funding_rate", "0")
            est_str = item.get("estimated_rate", None)
            fr = decimal.Decimal(est_str if est_str not in (None, "") else fr_str)
            fr = fr.quantize(decimal.Decimal("1E-6"))

            next_ms = int(item.get("next_funding_time", 0) or 0)
            next_dt = datetime.fromtimestamp(next_ms / 1000, tz=timezone.utc) if next_ms else None
            countdown = (next_dt - datetime.now(timezone.utc)).total_seconds() if next_dt else 0

            timestamp = datetime.now(timezone.utc).isoformat()
            logger.info(f"[Huobi] {symbol} funding fetched at {timestamp}, next in {countdown:.0f}s")

            return {
                "ticker": symbol,
                "funding_rate": fr,
                "funding_timestamp_utc": timestamp,
                "next_funding_utc": next_dt.isoformat() if next_dt else None,
                "countdown_sec": countdown,
            }
        except Exception as e:
            logger.error(f"[Huobi] Error fetch funding for {symbol}: {e}")
            return {
                "ticker": symbol,
                "funding_rate": decimal.Decimal("0"),
                "funding_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "next_funding_utc": None,
                "countdown_sec": 0,
            }

    def calculate_profit(self, fr: decimal.Decimal, contract: Dict[str, Any]) -> decimal.Decimal:
        return fr - (contract["makerFeeRate"] + contract["takerFeeRate"])

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
                    logger.error(f"[Huobi] Analyze error {contract['symbol']}: {e}")
        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            results = self.analyze()
            logger.info(f"[Huobi] Completed: {len(results)}")
            return results
        except Exception as e:
            logger.error(f"[Huobi] GLOBAL error: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = HuobiScreener()
    print(scr.run())
