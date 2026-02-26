import requests
import logging
import decimal
from datetime import datetime, timezone
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class HyperliquidScreener:
    INFO_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self):
        self.name = "Hyperliquid"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        logger.info(f"[Hyperliquid] Initialized")

    def get_predicted_fundings(self) -> List[Dict[str, Any]]:
        body = {"type": "predictedFundings"}
        try:
            r = self.session.post(self.INFO_URL, json=body, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"[Hyperliquid] Failed to fetch predictedFundings: {e}")
            return []

    def run(self) -> List[Dict[str, Any]]:
        output = []
        all_data = self.get_predicted_fundings()

        for asset in all_data:
            try:
                symbol = asset[0]
                exchanges = asset[1]
                # знайдемо саме HlPerp
                for ex_name, info in exchanges:
                    if ex_name == "HlPerp":
                        fr_str = info.get("fundingRate", "0")
                        ts_ms = info.get("nextFundingTime", None)

                        fr = decimal.Decimal(fr_str).quantize(decimal.Decimal("1E-6"))
                        next_dt = None
                        countdown = 0
                        if ts_ms:
                            next_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                            countdown = (next_dt - datetime.now(timezone.utc)).total_seconds()

                        timestamp = datetime.now(timezone.utc).isoformat()

                        output.append({
                            "ticker": symbol,
                            "funding_rate": fr,
                            "funding_timestamp_utc": timestamp,
                            "next_funding_utc": next_dt.isoformat() if next_dt else None,
                            "countdown_sec": countdown,
                            "potential_profit": fr  # Hyperliquid fees require custom logic
                        })
            except Exception as e:
                logger.error(f"[Hyperliquid] Error parsing asset data: {e}")

        return output

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    scr = HyperliquidScreener()
    print(scr.run())
