import csv
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from statistics import mean, median

import matplotlib.pyplot as plt

# ----------------- CONFIG -----------------
DIRS = ["results", "funding_results"]
OUTPUT_DIR = "analysis_output"
ROWS_SAMPLE_SYMBOLS = 10

Path(OUTPUT_DIR).mkdir(exist_ok=True)

# ----------------- HELPERS -----------------

def detect_delimiter(sample):
    """Авто-визначення роздільника CSV"""
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
    """Витяг часу з імені файлу"""
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

# ----------------- GRAPHING -----------------

def plot_time_distribution(file_times, prefix):
    """Графіки: погодинно та хвилинно всередині години"""
    if not file_times:
        return

    hours = Counter()
    minutes = Counter()
    for t in file_times:
        hours[t.replace(minute=0, second=0, microsecond=0)] += 1
        minutes[t.minute] += 1

    # hourly
    xs = sorted(hours.keys())
    ys = [hours[x] for x in xs]
    plt.figure(figsize=(12, 5))
    plt.plot(xs, ys, marker="o")
    plt.xticks(rotation=45)
    plt.title(f"Files per hour ({prefix})")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/{prefix}_files_per_hour.png")
    plt.close()

    # minute
    xs = sorted(minutes.keys())
    ys = [minutes[x] for x in xs]
    plt.figure(figsize=(10, 4))
    plt.bar(xs, ys)
    plt.title(f"Minute distribution ({prefix})")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/{prefix}_minute_distribution.png")
    plt.close()

# ----------------- MAIN ANALYSIS -----------------

def analyze_folder(folder):
    print("\n==============================")
    print(f"📂 ANALYSIS: {folder}")
    print("==============================")

    path = Path(folder)
    files = sorted([p for p in path.iterdir() if p.is_file()])
    print("FILES:", len(files))

    # ----------------- TIME ANALYSIS -----------------
    file_times = []
    total_rows = 0

    exchange_total_rows = Counter()
    exchange_funding_rows = Counter()
    exchange_symbols = defaultdict(set)

    for file in files:
        t = parse_filename_time(file.name)
        if t:
            file_times.append(t)
        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(4096)
                delim = detect_delimiter(sample)
                f.seek(0)
                reader = csv.DictReader(f, delimiter=delim)
                for row in reader:
                    total_rows += 1
                    exch = row.get("exchange")
                    sym = row.get("symbol") or row.get("ticker")
                    fr = parse_float(row.get("funding_rate"))
                    if exch:
                        exchange_total_rows[exch] += 1
                        if fr is not None:
                            exchange_funding_rows[exch] += 1
                            if sym:
                                exchange_symbols[exch].add(sym)
        except Exception as e:
            print("Error reading", file, e)

    # ---------- TIME STATS ----------
    if file_times:
        file_times.sort()
        intervals = [(file_times[i] - file_times[i - 1]).total_seconds() for i in range(1, len(file_times))]
        if intervals:
            print("\n⏱ Frequency seconds")
            print("avg:", round(mean(intervals),2))
            print("median:", round(median(intervals),2))
            print("min:", round(min(intervals),2))
            print("max:", round(max(intervals),2))
        print("\n🕒 Coverage")
        print("from:", file_times[0])
        print("to  :", file_times[-1])
        print("duration:", file_times[-1] - file_times[0])
    plot_time_distribution(file_times, folder)

    # ---------- FUNDING STATS ----------
    print("\nTOTAL ROWS:", total_rows)
    exchanges_all = set(exchange_total_rows.keys())
    exchanges_zero = sorted([exch for exch in exchanges_all if exchange_funding_rows.get(exch,0)==0])

    if exchanges_zero:
        print("\n❌ EXCHANGES WITH ZERO FUNDING DATA:")
        for e in exchanges_zero:
            print(" ", e)
    else:
        print("\n❌ No exchanges completely without funding")

    print("\n✅ FUNDING RECORDS PER EXCHANGE:")
    for exch in sorted(exchanges_all):
        total = exchange_total_rows[exch]
        funding = exchange_funding_rows.get(exch, 0)
        pct = funding / total * 100 if total else 0
        print(f"\n{exch}")
        print(f"  total rows: {total}")
        print(f"  funding rows: {funding}")
        print(f"  percent with funding: {pct:.2f}%")
        # приклади символів
        samples = list(exchange_symbols[exch])[:ROWS_SAMPLE_SYMBOLS]
        print("  symbols:")
        for s in samples:
            print("   ", s)

# ----------------- RUN -----------------

def main():
    for d in DIRS:
        analyze_folder(d)
    print("\nGraphs saved in:", OUTPUT_DIR)

if __name__ == "__main__":
    main()
    