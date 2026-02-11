import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta
import logging

logging.basicConfig(
    level=logging.INFO,
    filename="fetcher0.log",
    filemode="a",
    format="%(asctime)s %(levelname)s %(message)s"
)

BASE = "https://gamma-api.polymarket.com"
EVENTS_URL = BASE + "/events"
MARKETS_URL = BASE + "/markets"

OUT_EVENTS = "events_all.csv"
OUT_MARKETS = "markets_recent.csv"
SEMAPHORE = "data_up_to_date.flag"

PAGE_LIMIT = 500
RETRY_DELAYS = [1, 5, 20, 60]  # тільки послідовні затримки, без maxRetries


# -----------------------------
#   HTTP fetch with retry loop
# -----------------------------
def fetch_page(url, params):
#    print(params, url)
    for delay in RETRY_DELAYS:
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()

        except Exception as e:
            logging.warning(
                "Error fetch %s params=%s : %s — retry in %s sec",
                url, params, e, delay
            )
            time.sleep(delay)

    # якщо всі ретрі пройшли — повертаємо None
    logging.error("All retry delays exhausted for %s params=%s", url, params)
    return None


# -----------------------------
#   Fetch ALL events
# -----------------------------
def fetch_all_events():
    all_items = []
    offset = 0

    while True:
        params = {
            "limit": PAGE_LIMIT,
            "offset": offset
        }

        data = fetch_page(EVENTS_URL, params)
        if not data:
            break

        # Polymarket Gamma API може повертати list або dict
        if isinstance(data, list):
            items = data
        else:
            items = data.get("items") or data.get("data") or data

        if not items:
            break

        all_items.extend(items)
        logging.info("Events offset %d → %d items", offset, len(items))

        if len(items) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT

    return all_items


# -----------------------------
#   Fetch ALL markets (30 days)
# -----------------------------
def fetch_recent_markets():
    cutoff_min = datetime.utcnow() - timedelta(days=3)
    cutoff_max = datetime.utcnow() + timedelta(days=10)
    
    cutoff_min_iso = cutoff_min.isoformat() + "Z"
    cutoff_max_iso = cutoff_max.isoformat() + "Z"

    all_items = []
    offset = 0

    while True:
        params = {
            "limit": PAGE_LIMIT,
            "offset": offset,
#            "start_date_min": cutoff_min_iso,
            "end_date_min": cutoff_min_iso,
            "end_date_max": cutoff_max_iso,
        }

        data = fetch_page(MARKETS_URL, params)
        if not data:
            break

        if isinstance(data, list):
            items = data
        else:
            items = data.get("items") or data.get("data") or data

        if not items:
            break

        all_items.extend(items)
        logging.info("Markets offset %d → %d items", offset, len(items))

        if len(items) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT

    return all_items


# ----------------------------------------------------------
#    ВИКОНАННЯ КОДУ ОДРАЗУ — БЕЗ main(), ДАНІ ДОСТУПНІ
# ----------------------------------------------------------
fetch_events = False
if fetch_events:
    logging.info("=== Fetching EVENTS ===")
    events = fetch_all_events()
    df_events = pd.DataFrame(events)
    df_events.to_csv(OUT_EVENTS, index=False)
    logging.info("Saved %d events → %s", len(df_events), OUT_EVENTS)

fetch_markets = True
if fetch_markets:
    logging.info("=== Fetching MARKETS (30d) ===")
    markets = fetch_recent_markets()
    df_markets = pd.DataFrame(markets)
    df_markets.to_csv(OUT_MARKETS, index=False)
    logging.info("Saved %d markets → %s", len(df_markets), OUT_MARKETS)

# ------------------------
#   Semaphore file
# ------------------------
with open(SEMAPHORE, "w") as f:
    f.write("updated: " + datetime.utcnow().isoformat() + "\n")

logging.info("Semaphore created: %s", SEMAPHORE)
