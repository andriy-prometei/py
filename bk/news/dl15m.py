#!/usr/bin/env python3.11

import os
import sys
import requests
import logging
import zipfile
import time
from pathlib import Path
from datetime import datetime

# ================== CONFIG ==================

URLS = [
    "http://data.gdeltproject.org/gdeltv2/lastupdate.txt",
    "http://data.gdeltproject.org/gdeltv2/lastupdate-translation.txt",
]

BASE_DIR = Path(__file__).resolve().parent
DEST_DIR = BASE_DIR / "gdelt_data"
LOG_FILE = BASE_DIR / "gdelt_downloader.log"
PID_FILE = BASE_DIR / "gdelt_downloader.pid"

CHUNK_SIZE = 1024 * 1024  # 1 MB
TIMEOUT = 60

# ============================================

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s"
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(formatter)

    logger.addHandler(ch)
    logger.addHandler(fh)

def check_pid():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            # перевіряємо чи процес існує
            os.kill(pid, 0)
        except (ValueError, ProcessLookupError, PermissionError):
            logging.info(f"Stale PID file found. Overwriting.")
        else:
            logging.warning(f"Another instance (PID {pid}) is running. Exiting.")
            sys.exit(0)
    PID_FILE.write_text(str(os.getpid()))

def remove_pid():
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass

def download_file(url: str, dest: Path):
    if dest.exists():
        logging.info(f"SKIP  {dest.name}")
        return

    logging.info(f"DOWN  {dest.name}")
    try:
        with requests.get(url, stream=True, timeout=TIMEOUT) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
    except Exception as e:
        logging.error(f"FAIL  {dest.name}: {e}")
        if dest.exists():
            dest.unlink(missing_ok=True)

def unpack_zip(file_path: Path):
    if not file_path.exists() or not zipfile.is_zipfile(file_path):
        return
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(DEST_DIR)
        logging.info(f"UNZIP  {file_path.name}")
    except Exception as e:
        logging.error(f"UNZIP FAIL {file_path.name}: {e}")

def process_lastupdate(url: str):
    logging.info(f"PROCESS {url}")
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logging.error(f"Cannot fetch {url}: {e}")
        return

    for line in resp.text.strip().splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        file_url = parts[2]
        filename = file_url.split("/")[-1]
        dest_path = DEST_DIR / filename
        try:
            download_file(file_url, dest_path)
            unpack_zip(dest_path)
        except Exception as e:
            logging.error(f"Error processing {filename}: {e}")

def main():
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    for url in URLS:
        process_lastupdate(url)

if __name__ == "__main__":
    setup_logging()
    check_pid()
    logging.info("===== GDELT downloader started =====")
    try:
        main()
    except Exception as e:
        logging.exception("Fatal error")
    finally:
        logging.info("===== GDELT downloader finished =====")
        remove_pid()
