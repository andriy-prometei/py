# funding_raw_debug.py
import ccxt
import json
import os
from datetime import datetime
from pathlib import Path

# Список бірж, де next_funding_utc = None
PROBLEM_EXCHANGES = ['whitebit']
"""[
    'gate', 'lbank', 'bitmart', 'kraken', 'coinex',
    'kucoin', 'xt', 'coinbase', 'poloniex', 'bitget',
    'whitebit', 'huobi', 'bitmex', 'deribit'
]"""

OUTPUT_DIR = Path("funding_raw_debug")
OUTPUT_DIR.mkdir(exist_ok=True)


import ccxt
from datetime import datetime, timezone

def patch_funding_parsers():
    print("Applying funding parser patches...")

    # ===========
    # BITGET
    # ===========
    if hasattr(ccxt, "bitget"):
        original_bitget = ccxt.bitget.parse_funding_rate

        def patched_bitget(self, info, market=None):
            parsed = original_bitget(self, info, market)

            if isinstance(info, dict) and info.get("nextUpdate"):
                try:
                    ts = int(info["nextUpdate"])
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.bitget.parse_funding_rate = patched_bitget

    # ===========
    # BITMART
    # ===========
    if hasattr(ccxt, "bitmart"):
        original_bitmart = ccxt.bitmart.parse_funding_rate

        def patched_bitmart(self, info, market=None):
            parsed = original_bitmart(self, info, market)

            if isinstance(info, dict) and info.get("funding_time"):
                try:
                    ts = int(info["funding_time"])
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.bitmart.parse_funding_rate = patched_bitmart

    # ===========
    # BITMEX
    # ===========
    if hasattr(ccxt, "bitmex"):
        original_bitmex = ccxt.bitmex.parse_funding_rate

        def patched_bitmex(self, info, market=None):
            parsed = original_bitmex(self, info, market)

            if isinstance(info, dict) and info.get("fundingTimestamp"):
                try:
                    iso = info["fundingTimestamp"]
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    ts = int(dt.timestamp() * 1000)

                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = dt.isoformat()

                except Exception:
                    pass

            return parsed

        ccxt.bitmex.parse_funding_rate = patched_bitmex

    # ===========
    # GATE
    # ===========
    if hasattr(ccxt, "gate"):
        original_gate = ccxt.gate.parse_funding_rate

        def patched_gate(self, info, market=None):
            parsed = original_gate(self, info, market)

            if isinstance(info, dict) and info.get("funding_next_apply"):
                try:
                    ts = int(info["funding_next_apply"]) * 1000
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.gate.parse_funding_rate = patched_gate

    # ===========
    # HUOBI
    # ===========
    if hasattr(ccxt, "huobi"):
        original_huobi = ccxt.huobi.parse_funding_rate

        def patched_huobi(self, info, market=None):
            parsed = original_huobi(self, info, market)

            # fallback якщо CCXT не поставив
            if parsed.get("nextFundingTimestamp") is None:

                ts = info.get("fundingTimestamp") or info.get("nextFundingTime")

                if ts:
                    try:
                        ts = int(ts)
                        parsed["nextFundingTimestamp"] = ts
                        parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                    except Exception:
                        pass

            return parsed

        ccxt.huobi.parse_funding_rate = patched_huobi

    # ===========
    # WHITEBIT
    # ===========
    if hasattr(ccxt, "whitebit"):
        original_whitebit = ccxt.whitebit.parse_funding_rate

        def patched_whitebit(self, info, market=None):
            parsed = original_whitebit(self, info, market)

            # ADD THIS CHECK: Ensure 'parsed' is not None before proceeding
            if parsed is None:
                return None

            if isinstance(info, dict) and info.get("next_funding_rate_timestamp"):
                try:
                    ts = int(info["next_funding_rate_timestamp"])
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.whitebit.parse_funding_rate = patched_whitebit

    # ===========
    # XT
    # ===========
    if hasattr(ccxt, "xt"):
        original_xt = ccxt.xt.parse_funding_rate

        def patched_xt(self, info, market=None):
            parsed = original_xt(self, info, market)

            if isinstance(info, dict) and info.get("nextCollectionTime"):
                try:
                    ts = int(info["nextCollectionTime"])
                    parsed["nextFundingTimestamp"] = ts
                    parsed["nextFundingDatetime"] = _ts_to_iso(ts)
                except Exception:
                    pass

            return parsed

        ccxt.xt.parse_funding_rate = patched_xt

    print("✅ Funding parser patches applied")


patch_funding_parsers()


def debug_funding_data(exchange_name: str, max_symbols: int = 5):
    print(f"\n{'='*30}")
    print(f"   {exchange_name.upper()}")
    print(f"{'='*30}")

    try:
        ex = getattr(ccxt, exchange_name)({
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {'defaultType': 'swap'},  # намагаємось perpetual
        })
        #fr_data = ex.fetch_funding_rate('BTC/USDT:USDT')
        #print(fr_data)
        #exit()

        markets = ex.load_markets()

        # Фільтруємо тільки активні perpetual (безстрокові)
        perps = [
            sym for sym, m in markets.items()
            if m.get('swap') and m.get('active', False) and not m.get('expiry')
        ]

        if not perps:
            print("Не знайдено активних perpetual контрактів")
            return

        print(f"Знайдено perpetual контрактів: {len(perps)}")
        print("Перші 5:", ", ".join(perps[:5]) or "—")

        # Беремо перші кілька символів для тесту
        symbols_to_check = perps[:max_symbols]
        print('symbols_to_check', symbols_to_check)

        results = {}

        for symbol in symbols_to_check:
            try:
                fr_data = ex.fetch_funding_rate(symbol)
                key = f"{symbol}__funding_rate"
                results[key] = {
                    "fetched_at": datetime.utcnow().isoformat() + "Z",
                    "symbol": symbol,
                    "funding_rate": fr_data.get("fundingRate"),
                    "last_funding_rate": fr_data.get("lastFundingRate"),
                    "raw_full_response": fr_data,
                }
                print(f"✓ {symbol:20} → fundingRate = {fr_data.get('fundingRate')}")
            except Exception as e:
                print(f"✗ {symbol:20} → {type(e).__name__}: {e}")

        # Зберігаємо результат
        if results:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = OUTPUT_DIR / f"{exchange_name}_{ts}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            print(f"Збережено → {filename}")
        else:
            print("Не вдалося отримати жодного funding rate")

    except Exception as e:
        print(f"Критична помилка при ініціалізації {exchange_name}: {e}")


if __name__ == "__main__":
    for exch in PROBLEM_EXCHANGES:
        debug_funding_data(exch, max_symbols=4)   # 4 символи достатньо для аналізу структури
    print("\nГотово. Файли збережено в папку:", OUTPUT_DIR.resolve())
    