import os
import csv
import re
from pathlib import Path
from datetime import datetime
from statistics import mean, median
from collections import defaultdict, Counter


DIRS = ["results", "funding_results"]


# ---------- helpers ----------

def detect_delimiter(sample):
    import csv
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ","


def parse_float(x):
    try:
        return float(x)
    except:
        return None


def parse_ts(x):
    try:
        return datetime.fromisoformat(x.replace("Z", "+00:00"))
    except:
        return None


def parse_filename_time(name):
    patterns = [
        r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})",
        r"(\d{8}_\d{6})"
    ]

    for p in patterns:
        m = re.search(p, name)
        if m:
            s = m.group(1)
            try:
                if "-" in s:
                    return datetime.strptime(s, "%Y-%m-%d_%H-%M-%S")
                else:
                    return datetime.strptime(s, "%Y%m%d_%H%M%S")
            except:
                pass
    return None


# ---------- main analysis ----------

def analyze_folder(folder):

    path = Path(folder)

    if not path.exists():
        print(f"\n❌ Folder not found: {folder}")
        return

    print(f"\n==============================")
    print(f"📂 ANALYSIS: {folder}")
    print(f"==============================")

    files = sorted([p for p in path.iterdir() if p.is_file()])

    if not files:
        print("No files")
        return

    file_times = []
    row_counts = []
    exchanges = set()
    symbols = set()
    funding_values = []

    ts_min = None
    ts_max = None

    rows_per_file = {}

    empty_fields = 0
    total_fields = 0

    for file in files:

        fname_time = parse_filename_time(file.name)
        if fname_time:
            file_times.append(fname_time)

        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:

                sample = f.read(4096)
                delim = detect_delimiter(sample)
                f.seek(0)

                reader = csv.DictReader(f, delimiter=delim)

                count = 0

                for row in reader:
                    count += 1

                    # exchange
                    exch = row.get("exchange")
                    if exch:
                        exchanges.add(exch)

                    # symbol / ticker
                    sym = row.get("symbol") or row.get("ticker")
                    if sym:
                        symbols.add(sym)

                    # funding
                    fr = parse_float(row.get("funding_rate"))
                    if fr is not None:
                        funding_values.append(fr)

                    # timestamp
                    ts = parse_ts(row.get("funding_timestamp_utc", ""))
                    if ts:
                        if ts_min is None or ts < ts_min:
                            ts_min = ts
                        if ts_max is None or ts > ts_max:
                            ts_max = ts

                    # empty fields
                    for v in row.values():
                        total_fields += 1
                        if v in ("", None):
                            empty_fields += 1

                row_counts.append(count)
                rows_per_file[file.name] = count

        except Exception as e:
            print("Error reading", file, e)

    # ---------- stats ----------

    print("\nFILES:", len(files))

    if file_times:
        file_times.sort()
        intervals = [
            (file_times[i] - file_times[i - 1]).total_seconds()
            for i in range(1, len(file_times))
        ]

        if intervals:
            print("\n⏱ Collection frequency (seconds)")
            print("avg:", round(mean(intervals), 2))
            print("median:", round(median(intervals), 2))
            print("min:", round(min(intervals), 2))
            print("max:", round(max(intervals), 2))

    if row_counts:
        print("\n📊 Rows per file")
        print("avg:", round(mean(row_counts), 2))
        print("median:", round(median(row_counts), 2))
        print("min:", min(row_counts))
        print("max:", max(row_counts))

    print("\n🏦 Exchanges:", len(exchanges))
    print(list(exchanges)[:20])

    print("\n💱 Symbols:", len(symbols))

    if ts_min and ts_max:
        print("\n🕒 Time coverage")
        print("from:", ts_min)
        print("to  :", ts_max)
        print("duration:", ts_max - ts_min)

    if funding_values:
        print("\n💰 Funding stats")
        print("min:", min(funding_values))
        print("max:", max(funding_values))
        print("avg:", mean(funding_values))

    if total_fields:
        empty_pct = empty_fields / total_fields * 100
        print("\n📉 Empty fields %:", round(empty_pct, 2))


# ---------- run ----------

def main():
    for d in DIRS:
        analyze_folder(d)


if __name__ == "__main__":
    main()