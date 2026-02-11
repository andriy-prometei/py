#!/usr/bin/env python3
"""
Polymarket CLOB market websocket listener (market channel)
Filtered subscription, log flags, append logs mode.
"""

import asyncio
import aiohttp
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Tuple, List

# ----------------------
# Config
# ----------------------

# Write control flags
WRITE_RAW = True          # write per-market raw packets
WRITE_BOOK = False         # write book snapshots
WRITE_GLOBAL_RAW = False   # write unmatched raw packets into global_raw.log

WS_BASE = "wss://ws-subscriptions-clob.polymarket.com"
CHANNEL = "market"
WS_URL = WS_BASE + "/ws/" + CHANNEL

MARKETS_CSV = "markets_recent.csv"
OUT_DIR = "ws_logs"
RUN_FLAG = "ws_listener.running"
REFRESH_FLAG = "data_up_to_date.flag"

PING_INTERVAL = 5
CHECK_INTERVAL = 5
RECONNECT_DELAYS = [1, 3, 10, 30, 60]

# filtering words for skipping markets
FILTER_WORDS = ["btc", "bitcoin", "eth", "xrp", "sol", "musk"]

logging.basicConfig(
    level=logging.INFO,
    filename="ws-listener0.log",
    filemode="a",
    format="%(asctime)s %(levelname)s %(message)s",
#    handlers=[logging.StreamHandler(sys.stdout)]
)

os.makedirs(OUT_DIR, exist_ok=True)

# ----------------------
# Utilities
# ----------------------
def now_ts() -> int:
    return int(time.time())

def sanitize_slug(s: str) -> str:
    return ''.join(c if c.isalnum() or c in "-_." else "_" for c in s)[:200]

def skip_slug(slug: str) -> bool:
    s = slug.lower()
    return any(w in s for w in FILTER_WORDS)

def parse_first_token(row: Dict[str, str]) -> str:
    for key in ("clobTokenIds", "clob_token_ids", "tokenIds", "tokens", "clobTokenIdsStr"):
        v = row.get(key)
        if not v:
            continue
        try:
            lst = json.loads(v) if isinstance(v, str) else v
            if isinstance(lst, list) and lst:
                return str(lst[0])
        except:
            s = v.strip().strip("[]")
            parts = [p.strip().strip('"').strip("'") for p in s.split(",") if p.strip()]
            if parts:
                return parts[0]
    for k in ("id", "marketId", "market_id"):
        if row.get(k):
            return str(row[k])
    for k in ("slug", "ticker", "question"):
        if row.get(k):
            return sanitize_slug(str(row[k]))
    return ""

def load_markets(csv_path: str) -> Dict[str, Tuple[str,str]]:
    mapping = {}
    if not os.path.exists(csv_path):
        logging.warning("Markets CSV not found: %s", csv_path)
        return mapping
    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                slug = sanitize_slug(str(r.get("slug") or r.get("ticker") or r.get("question") or ""))
                if skip_slug(slug):
                    continue
                mid = r.get("id") or r.get("conditionId") or r.get("marketId") or r.get("market_id") or ""
                token = parse_first_token(r)
                if token:
                    mapping[token] = (mid or token, slug)
    except Exception:
        logging.exception("Failed to read markets CSV")

    logging.info("Loaded %d tokens after filtering", len(mapping))
    return mapping

class MarketFiles:
    def __init__(self, slug: str, market_id):
        ts = now_ts()
        safe = sanitize_slug(slug)
        base = os.path.join(OUT_DIR, f"{safe}.{market_id}")
        self.raw_path = base + ".raw.log"
        self.book_path = base + ".book.csv"
        self.last_raw = None

        if WRITE_BOOK:
            try:
                with open(self.book_path, "a", encoding="utf-8") as f:
                    f.write("ts,book_json\n")
            except:
                logging.exception("init book file failed for %s", self.book_path)

    def write_raw(self, pkt: dict):
        if not WRITE_RAW:
            return
        try:
            key = json.dumps(pkt, sort_keys=True)
            if key == self.last_raw:
                return
            self.last_raw = key
            with open(self.raw_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": now_ts(), "p": pkt}, ensure_ascii=False) + "\n")
        except:
            logging.exception("write_raw failed for %s", self.raw_path)

    def write_book(self, book_obj):
        if not WRITE_BOOK:
            return
        try:
            with open(self.book_path, "a", encoding="utf-8") as f:
                line = json.dumps(book_obj, ensure_ascii=False).replace("\n", "\\n")
                f.write(f"{now_ts()},{line}\n")
        except:
            logging.exception("write_book failed for %s", self.book_path)

# ----------------------
# Listener
# ----------------------
class WSListener:
    def __init__(self):
        self.token_to_market = {}
        self.market_files = {}
        self.assets_list = []
        self.session = None
        self.ws = None
        self.stop_requested = False

    def load_and_prepare(self):
        mt = load_markets(MARKETS_CSV)
        self.token_to_market = mt
        self.assets_list = list(mt.keys())
        for token, (mid, slug) in mt.items():
            if mid not in self.market_files:
                self.market_files[mid] = MarketFiles(slug, mid)

    async def connect(self) -> bool:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        for delay in RECONNECT_DELAYS:
            try:
                logging.info("Connecting to WS %s", WS_URL)
                self.ws = await self.session.ws_connect(WS_URL, heartbeat=PING_INTERVAL)
                logging.info("WS connected")
                return True
            except Exception as e:
                logging.warning("WS connect failed: %s — retry in %s s", e, delay)
                await asyncio.sleep(delay)
        return False

    async def disconnect(self):
        try:
            if self.ws:
                await self.ws.close()
        except:
            pass
        try:
            if self.session:
                await self.session.close()
        except:
            pass
        self.ws = None
        self.session = None

    async def subscribe_assets(self):
        if not self.ws:
            return
        try:
            msg = {"assets_ids": self.assets_list, "type": "market"}
            await self.ws.send_json(msg)
            logging.info("Subscribed to %d markets", len(self.assets_list))
        except:
            logging.exception("Failed to send subscribe message")

    async def handle_message(self, msg_text: str):
        try:
            payload = json.loads(msg_text)
        except:
            payload = {"raw": msg_text}

        token = payload.get("asset_id") or payload.get("assetId")
        if token and token in self.token_to_market:
            mid, slug = self.token_to_market[token]
            mf = self.market_files[mid]
            mf.write_raw(payload)
        else:
            if WRITE_GLOBAL_RAW:
                try:
                    with open(os.path.join(OUT_DIR, "global_raw.log"), "a", encoding="utf-8") as f:
                        f.write(json.dumps({"ts": now_ts(), "p": payload}, ensure_ascii=False) + "\n")
                except:
                    logging.exception("global raw write failed")

        if payload.get("event_type") == "book" and token in self.token_to_market:
            mid, slug = self.token_to_market[token]
            mf = self.market_files[mid]
            mf.write_book(payload)

    async def receiver_loop(self):
        while True:
            if not os.path.exists(RUN_FLAG):
                return

            if self.ws is None or self.ws.closed:
                ok = await self.connect()
                if ok:
                    await self.subscribe_assets()
                else:
                    await asyncio.sleep(3)
                    continue

            try:
                msg = await self.ws.receive(timeout=PING_INTERVAL + 10)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.handle_message(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    await self.disconnect()
            except asyncio.TimeoutError:
                try:
                    await self.ws.ping()
                except:
                    pass
                try:
                    await self.ws.send_str("PING")
                except:
                    pass
            except:
                await self.disconnect()
                await asyncio.sleep(1)

    async def periodic_loop(self):
        while True:
            if not os.path.exists(RUN_FLAG):
                return

            if os.path.exists(REFRESH_FLAG):
                logging.info("REFRESH_FLAG detected — reloading markets")
                old_assets = self.assets_list.copy()
                self.load_and_prepare()
                if self.ws and not self.ws.closed:
                    if self.assets_list != old_assets:
                        await self.subscribe_assets()
                try:
                    os.remove(REFRESH_FLAG)
                except:
                    logging.exception("Failed to remove REFRESH_FLAG")

            await asyncio.sleep(CHECK_INTERVAL)

    async def run(self):
        try:
            with open(RUN_FLAG, "w") as f:
                f.write(f"pid:{os.getpid()} ts:{now_ts()}\n")
        except:
            pass

        self.load_and_prepare()
        await self.connect()
        if self.ws:
            await self.subscribe_assets()

        receiver = asyncio.create_task(self.receiver_loop())
        periodic = asyncio.create_task(self.periodic_loop())

        await asyncio.wait([receiver, periodic], return_when=asyncio.FIRST_COMPLETED)

        receiver.cancel()
        periodic.cancel()
        await self.disconnect()

        try:
            if os.path.exists(RUN_FLAG):
                os.remove(RUN_FLAG)
        except:
            pass

async def main():
    listener = WSListener()
    await listener.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Interrupted")
    except Exception:
        logging.exception("Fatal error in ws-listener")
