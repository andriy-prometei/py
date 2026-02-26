import csv
from pathlib import Path

# Папка для перевірки
FOLDER = "funding_results"

path = Path(FOLDER)
files = sorted([p for p in path.iterdir() if p.is_file()])

for file in files:
    found = False
    try:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            sample = f.read(4096)
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                val = row.get("next_funding_utc")
                if val and val.strip():  # якщо поле не пусте
                    found = True
                    break
    except Exception as e:
        print("Error reading", file, e)

    print(f"{file.name}: {'YES' if found else 'NO'}")