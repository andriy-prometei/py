import os
import time
import json
import requests
import pandas as pd
import threading
from bs4 import BeautifulSoup


class WundergroundParser:
    HEADERS = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html",
        "Referer": "https://www.google.com/"
    }

    def __init__(self, save_folder="weather_data"):
        self.save_folder = save_folder
        os.makedirs(save_folder, exist_ok=True)

    # ---------------------------------------------------
    # 1. Load embed JSON
    # ---------------------------------------------------
    def fetch_embed_json(self, url: str) -> dict:
        try:
            r = requests.get(url, headers=self.HEADERS, timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f"[ERROR] Failed to fetch URL {url}: {e}")
            return {}

        soup = BeautifulSoup(r.text, "html.parser")
        script = soup.find("script", {"type": "application/json"})
        if not script:
            print(f"[WARN] No embed JSON found in page: {url}")
            return {}

        try:
            return json.loads(script.text.strip())
        except Exception as e:
            print(f"[ERROR] JSON parse failed for {url}: {e}")
            return {}

    # ---------------------------------------------------
    # 2. Extract daily + hourly DataFrames
    # ---------------------------------------------------
    def extract_forecast_tables(self, embed_json: dict):
        result = {
            "daily": pd.DataFrame(),
            "hourly": pd.DataFrame()
        }

        def walk(node):
            if isinstance(node, dict):

                if "u" in node and "b" in node:
                    u = node["u"]
                    b = node["b"]

                    if isinstance(b, dict):
                        try:
                            df = pd.DataFrame(b)
                        except Exception:
                            df = None

                        if df is not None:
                            if "/forecast/daily/10day" in u:
                                result["daily"] = df
                            elif "/forecast/hourly/15day" in u:
                                result["hourly"] = df

                for v in node.values():
                    walk(v)

            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(embed_json)
        return result

    # ---------------------------------------------------
    # 3. Save CSV only if dataframe is NOT empty
    # ---------------------------------------------------
    def save_nonempty(self, city: str, dfs: dict):
        timestamp = int(time.time())
        saved_paths = []

        for key in ["daily", "hourly"]:
            df = dfs[key]
            if not df.empty:
                fname = f"{city}_{key}_{timestamp}.csv"
                fpath = os.path.join(self.save_folder, fname)
                df.to_csv(fpath, index=False)
                saved_paths.append(fpath)
                print(f"[OK] Saved {key} for {city}: {fpath}")
            else:
                print(f"[SKIP] {key} for {city} is empty.")

        return saved_paths

    # ---------------------------------------------------
    # 4. Full process for a city
    # ---------------------------------------------------
    def process_city(self, city: str, url: str):
        print(f"[INFO] Processing {city} ...")
        embed = self.fetch_embed_json(url)
        dfs = self.extract_forecast_tables(embed)
        self.save_nonempty(city, dfs)


# =======================================================
# RUN PARSER FOR ALL CITIES — MULTITHREADED
# =======================================================

CITIES = {
    "London": "https://www.wunderground.com/forecast/gb/london/EGLC",
    "NY": "https://www.wunderground.com/forecast/us/ny/new-york-city/KLGA",
    "Dallas": "https://www.wunderground.com/forecast/us/tx/dallas/KDAL",
    "Atlanta": "https://www.wunderground.com/forecast/us/ga/atlanta/KATL",
    "Seattle": "https://www.wunderground.com/forecast/us/wa/seatac/KSEA",
    "Toronto": "https://www.wunderground.com/forecast/ca/mississauga/CYYZ",
    "Seoul": "https://www.wunderground.com/forecast/kr/incheon/RKSI",
    "BAires": "https://www.wunderground.com/forecast/ar/ezeiza/SAEZ"
}


def run_all():
    parser = WundergroundParser()

    threads = []
    for city, url in CITIES.items():
        t = threading.Thread(target=parser.process_city, args=(city, url))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    run_all()

