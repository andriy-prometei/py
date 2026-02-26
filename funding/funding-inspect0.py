import os
import csv
from pathlib import Path

DIRS = ["results", "funding_results"]
FILES_TO_SHOW = 3
ROWS_TO_SHOW = 5


def detect_delimiter(sample):
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ","


def preview_csv(file_path):
    print(f"\n📄 FILE: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            sample = f.read(4096)
            delimiter = detect_delimiter(sample)
            f.seek(0)

            reader = csv.reader(f, delimiter=delimiter)

            header = next(reader, None)
            print("HEADER:", header)

            print("SAMPLES:")
            for i, row in enumerate(reader):
                print(row)
                if i + 1 >= ROWS_TO_SHOW:
                    break

    except Exception as e:
        print("ERROR:", e)


def inspect_folder(folder):
    path = Path(folder)

    if not path.exists():
        print(f"\n❌ Folder not found: {folder}")
        return

    print(f"\n==============================")
    print(f"📂 FOLDER: {folder}")
    print(f"==============================")

    files = sorted([p for p in path.iterdir() if p.is_file()])

    print("\nFILES:")
    for f in files[:FILES_TO_SHOW]:
        print(f.name)

    for f in files[:FILES_TO_SHOW]:
        preview_csv(f)


def main():
    for d in DIRS:
        inspect_folder(d)


if __name__ == "__main__":
    main()
    