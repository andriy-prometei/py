import ccxt.async_support as ccxt
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_DIR = Path("funding_async_debug")
OUTPUT_DIR.mkdir(exist_ok=True)


# Список бірж, де next_funding_utc = None
PROBLEM_EXCHANGES = [
    "binance",
    "bitmart",
    "toobit",
    "xt",
    "phemex",
    "coinbase",
    "coinex",
    "coinbaseadvanced",
    "huobi",
    "bingx",
    "htx",
    "bydfi",
    "kucoin",
    "mexc",
    "coinbaseexchange",
    "ascendex",
    "blofin",
    "upbit",
    "kraken",
    "aster",
    "whitebit",
    "bitget",
    "okxus",
    "gateio",
    "gate",
    "cryptocom",
    "bitso",
    "backpack",
    "independentreserve",
    "okx",
    "blockchaincom",
    "apex",
    "bybit",
    "arkham",
    "bigone",
    "bitrue",
    "cryptomus",
    "hashkey",
    "digifinex",
    "ndax",
    "latoken",
    "myokx",
    "bitfinex",
    "deribit",
    "poloniex",
    "derive",
    "hitbtc",
    "alp",
    "hollaex",
    "cex",
    "bitmex",
    "coinsph",
    "onetrading",
    "fmfwio",
    "bitstamp",
    "coinbaseinternational",
    "timex",
    "zaif",
    "deepcoin",
    "bitteam",
    "bitopro",
    "foxbit",
    "defx",
    "novadax",
    "coinspot",
    "coincatch",
    "wavesexchange",
    "delta",
    "bequant",
    "bitbns",
    "lbank",
    "modetrade",
    "btcturk",
    "p2b",
    "paradex",
    "exmo",
    "dydx",
    "bit2c",
    "woo",
    "woofipro",
    "indodax",
    "btcbox",
    "gemini",
    "btcmarkets",
    "zonda",
    "bittrade",
    "zebpay",
    "bithumb",
    "coinone",
    "mercado",
    "oxfun",
    "binanceus",
    "bitvavo",
    "paymium",
    "bullish",
    "hibachi",
    "coincheck",
    "luno",
    "bitbank",
    "bitflyer",
    "alpaca",
]


# ---------- Патчі для парсингу nextFunding (ідентичні оригіналу) ----------
def patch_funding_parsers():
    print("Applying funding parser patches...")

    # ===========
    # BITGET
    # ===========
    if hasattr(ccxt, "bitget"):
        original_bitget = ccxt.bitget.parse_funding_rate

        def patched_bitget(self, info, market=None):
            parsed = original_bitget(self, info, market)

            raw = info or {}

            # ---- next funding timestamp fallback ----
            if parsed.get("nextFundingTimestamp") is None:
                next_update = raw.get("nextUpdate")
                if next_update:
                    try:
                        ts = int(next_update)
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
    # DELTA
    # ===========
    if hasattr(ccxt, "delta"):
        original_delta = ccxt.delta.parse_funding_rate

        def patched_delta(self, info, market=None):
            parsed = original_delta(self, info, market)

            raw = info or {}
            quotes = raw.get("quotes") or {}

            best_bid = quotes.get("best_bid")
            best_ask = quotes.get("best_ask")
            bid_size = quotes.get("bid_size")
            ask_size = quotes.get("ask_size")

            # ---- price ----
            if best_bid is not None:
                try:
                    parsed["bid"] = float(best_bid)
                except Exception:
                    pass

            if best_ask is not None:
                try:
                    parsed["ask"] = float(best_ask)
                except Exception:
                    pass

            # ---- volumes ----
            if bid_size is not None:
                try:
                    parsed["bid_vol"] = float(bid_size)
                except Exception:
                    pass

            if ask_size is not None:
                try:
                    parsed["ask_vol"] = float(ask_size)
                except Exception:
                    pass

            return parsed

        ccxt.delta.parse_funding_rate = patched_delta

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
    # PHEMEX
    # ===========
    if hasattr(ccxt, "phemex"):
        original_phemex = ccxt.phemex.parse_funding_rate

        def patched_phemex(self, info, market=None):
            parsed = original_phemex(self, info, market)

            raw = info or {}

            bid_ep = raw.get("bidEp")
            ask_ep = raw.get("askEp")

            # Phemex prices are Ep = price * 1e4
            scale = 10000.0

            if bid_ep is not None:
                try:
                    parsed["bid"] = float(bid_ep) / scale
                except Exception:
                    pass

            if ask_ep is not None:
                try:
                    parsed["ask"] = float(ask_ep) / scale
                except Exception:
                    pass

            return parsed

        ccxt.phemex.parse_funding_rate = patched_phemex

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

def _ts_to_iso(ts):
    try:
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None

# =========================================================
# MAIN ASYNC DEBUG FUNCTION
# =========================================================
async def debug_exchange_async(exchange_name: str, max_symbols: int = 10):

    results = {}
    exchange_log = {
        "exchange": exchange_name,
        "calls": []
    }

    now_ms = int(datetime.utcnow().timestamp() * 1000)

    # ---------- FUTURES CLIENT ----------
    futures = getattr(ccxt, exchange_name)({
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
    })

    # ---------- SPOT CLIENT (fallback) ----------
    spot = getattr(ccxt, exchange_name)({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })

    try:
        # =====================================================
        # LOAD MARKETS
        # =====================================================
        markets = await futures.load_markets()
        exchange_log["calls"].append({
            "method": "load_markets",
            "args": {},
            "returned_markets_count": len(markets)
        })

        perps = [
            s for s, m in markets.items()
            if m.get("swap") and m.get("active") and not m.get("expiry")
        ]

        symbols = perps[:max_symbols]

        # =====================================================
        # BULK FUNDING
        # =====================================================
        funding_bulk = {}

        try:
            funding_bulk = await futures.fetch_funding_rates(symbols)
            exchange_log["calls"].append({
                "method": "fetch_funding_rates",
                "args": {"symbols": symbols},
                "returned_count": len(funding_bulk)
            })
        except Exception as e:
            exchange_log["calls"].append({
                "method": "fetch_funding_rates",
                "error": str(e)
            })

        # fallback to single
        if not funding_bulk:
            funding_bulk = {}
            for s in symbols:
                try:
                    fr = await futures.fetch_funding_rate(s)
                    funding_bulk[s] = fr
                    exchange_log["calls"].append({
                        "method": "fetch_funding_rate",
                        "args": {"symbol": s},
                        "returned": True
                    })
                except Exception as e:
                    exchange_log["calls"].append({
                        "method": "fetch_funding_rate",
                        "args": {"symbol": s},
                        "error": str(e)
                    })

        # =====================================================
        # BULK ORDERBOOKS (ASYNC GATHER)
        # =====================================================
        async def get_futures_ob(symbol):
            try:
                ob = await futures.fetch_order_book(symbol, 20)
                return symbol, ob, None
            except Exception as e:
                return symbol, None, str(e)

        futures_tasks = [get_futures_ob(s) for s in symbols]
        futures_orderbooks = await asyncio.gather(*futures_tasks)

        # =====================================================
        # PROCESS EACH SYMBOL
        # =====================================================
        for symbol in symbols:

            fr_raw = funding_bulk.get(symbol)
            futures_ob_raw = None
            futures_best_bid = None
            futures_best_ask = None

            # ---- funding values ----
            funding_rate = None
            next_ts = None
            seconds_left = None

            if fr_raw:
                funding_rate = fr_raw.get("fundingRate")
                next_ts = fr_raw.get("nextFundingTimestamp")

                if next_ts:
                    seconds_left = int((next_ts - now_ms) / 1000)

            # ---- futures OB ----
            for s, ob, err in futures_orderbooks:
                if s == symbol:
                    futures_ob_raw = ob
                    if ob:
                        futures_best_bid = ob["bids"][0][0] if ob["bids"] else None
                        futures_best_ask = ob["asks"][0][0] if ob["asks"] else None

            # =====================================================
            # SPOT ORDERBOOK (try futures client first)
            # =====================================================
            base_symbol = symbol.split(":")[0]
            spot_ob_raw = None
            spot_best_bid = None
            spot_best_ask = None

            try:
                spot_ob_raw = await futures.fetch_order_book(base_symbol, 20)
                exchange_log["calls"].append({
                    "method": "fetch_order_book",
                    "args": {"symbol": base_symbol, "via": "futures_client"}
                })
            except:
                try:
                    spot_ob_raw = await spot.fetch_order_book(base_symbol, 20)
                    exchange_log["calls"].append({
                        "method": "fetch_order_book",
                        "args": {"symbol": base_symbol, "via": "spot_client"}
                    })
                except Exception as e:
                    exchange_log["calls"].append({
                        "method": "fetch_order_book",
                        "args": {"symbol": base_symbol},
                        "error": str(e)
                    })

            if spot_ob_raw:
                spot_best_bid = spot_ob_raw["bids"][0][0] if spot_ob_raw["bids"] else None
                spot_best_ask = spot_ob_raw["asks"][0][0] if spot_ob_raw["asks"] else None

            # =====================================================
            # SAVE STRUCTURE
            # =====================================================
            results[symbol] = {
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "symbol": symbol,

                "funding_rate": funding_rate,
                "next_funding_timestamp": next_ts,
                "seconds_to_next_funding": seconds_left,

                "futures_best_bid": futures_best_bid,
                "futures_best_ask": futures_best_ask,

                "spot_best_bid": spot_best_bid,
                "spot_best_ask": spot_best_ask,

                "raw_funding": fr_raw,
                "raw_futures_orderbook": futures_ob_raw,
                "raw_spot_orderbook": spot_ob_raw,
            }

        # =====================================================
        # SAVE JSON
        # =====================================================
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = OUTPUT_DIR / f"{exchange_name}_bulk_async_full_debug_{ts}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "exchange_log": exchange_log,
                "symbols_data": results
            }, f, indent=2, default=str)

        print(f"✅ Saved {filename}")

    finally:
        await futures.close()
        await spot.close()


# =========================================================
# RUN ALL
# =========================================================
async def main():
    for exch in PROBLEM_EXCHANGES:
        print(f"\n==== {exch} ====")
        try:
            await debug_exchange_async(exch, max_symbols=5)
        except Exception as e:
            print("Fatal:", e)

asyncio.run(main())
