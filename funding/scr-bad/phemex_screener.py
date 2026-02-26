import requests
import decimal
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class PhemexScreener:
    BASE_URL = "https://api.phemex.com"
    PRODUCTS_ENDPOINT = "/exchange/public/products"

    def __init__(self):
        self.name = "Phemex"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Funding-Screener"})
        self.contracts = self.get_all_contracts()
        logger.info(f"[Phemex] Loaded {len(self.contracts)} perpetual contracts")

    def safe_get(self, url, retries=3):
        for i in range(retries):
            try:
                r = self.session.get(url, timeout=7)
                r.raise_for_status()
                return r.json()
            except Exception:
                if i == retries - 1:
                    raise

    def normalize_products_response(self, resp):
        """Гарантує, що ми обробляємо список контрактів незалежно від форми відповіді."""
        # 1) Якщо це dict із ключем 'data'
        if isinstance(resp, dict):
            # Якщо ключ "data" містить список
            data = resp.get("data")
            if isinstance(data, dict):
                products = data.get("products")
                if isinstance(products, list):
                    return products
            # Якщо верхній dict має ключ directly "products"
            products = resp.get("products")
            if isinstance(products, list):
                return products
            # Якщо це вже список всередині dict
            # інколи API може мати інші назви — просто повертаємо None
            return []
        # 2) Якщо це список — повертаємо його напряму
        if isinstance(resp, list):
            return resp
        return []

    def get_all_contracts(self) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}{self.PRODUCTS_ENDPOINT}"
        try:
            resp = self.safe_get(url)
        except Exception as e:
            logger.error(f"[Phemex] Failed GET products: {e}")
            return []

        products = self.normalize_products_response(resp)
        contracts = []
        for p in products:
            if not isinstance(p, dict):
                continue
            if p.get("type") != "Perpetual":
                continue
            # status may be in different key names
            if p.get("status") not in ("Listed", "ACTIVE", None):
                continue

            try:
                fr = decimal.Decimal(str(p.get("fundingRate", "0")))
            except Exception:
                fr = decimal.Decimal("0")

            try:
                next_ts = int(p.get("nextFundingTime", 0))
            except Exception:
                next_ts = 0

            try:
                maker = decimal.Decimal(str(p.get("makerFeeRate", "0")))
            except Exception:
                maker = decimal.Decimal("0")
            try:
                taker = decimal.Decimal(str(p.get("takerFeeRate", "0")))
            except Exception:
                taker = decimal.Decimal("0")

            contracts.append({
                "symbol": p.get("symbol"),
                "fundingRate": fr,
                "nextFundingTime": next_ts,
                "makerFeeRate": maker,
                "takerFeeRate": taker,
            })

        return contracts

    def process_contract(self, c: Dict[str, Any]) -> Dict[str, Any]:
        fr = c["fundingRate"].quantize(decimal.Decimal("1E-6"))

        next_dt_iso = None
        countdown = 0
        try:
            if c["nextFundingTime"]:
                next_ts = c["nextFundingTime"] / 1000
                next_dt = datetime.fromtimestamp(next_ts, tz=timezone.utc)
                next_dt_iso = next_dt.isoformat()
                countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()
        except Exception:
            pass

        ts_now = datetime.now(timezone.utc).isoformat()
        logger.info(f"[Phemex] {c['symbol']} funding {fr} | next in {countdown:.0f}s")

        return {
            "ticker": c["symbol"],
            "funding_rate": fr,
            "funding_timestamp_utc": ts_now,
            "next_funding_utc": next_dt_iso,
            "countdown_sec": countdown,
            "potential_profit": fr - (c["makerFeeRate"] + c["takerFeeRate"]),
        }

    def analyze(self) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(self.process_contract, c) for c in self.contracts]
            for f in as_completed(futures):
                try:
                    results.append(f.result())
                except Exception as e:
                    logger.error(f"[Phemex] contract failed: {e}")

        results.sort(key=lambda x: x["potential_profit"], reverse=True)
        return results

    def run(self):
        try:
            return self.analyze()
        except Exception as e:
            logger.error(f"[Phemex] GLOBAL ERROR: {e}")
            return []

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = PhemexScreener()
    print(scr.run()[:5])
