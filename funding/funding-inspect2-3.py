import os
import glob
import pandas as pd
from datetime import datetime


def analyze_latest_funding_file(folder='funding_results'):
    # Знаходимо останній файл
    files = glob.glob(os.path.join(folder, 'funding_*.csv'))
    if not files:
        print("Папка funding_results порожня або не існує.")
        return

    latest_file = max(files, key=os.path.getmtime)
    print(f"\nОстанній файл: {os.path.basename(latest_file)}")
    print(f"Дата створення/зміни: {datetime.fromtimestamp(os.path.getmtime(latest_file)).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Повний шлях: {latest_file}\n")

    # Читаємо файл
    try:
        df = pd.read_csv(latest_file)
    except Exception as e:
        print(f"Помилка читання файлу: {e}")
        return

    # Перетворюємо next_funding_utc на datetime, помилки → NaT
    df['next_funding_dt'] = pd.to_datetime(df['next_funding_utc'], errors='coerce', utc=True)

    # Визначаємо, чи є значення next_funding_utc
    df['has_next'] = df['next_funding_dt'].notna()

    # Групуємо по біржах
    grouped = df.groupby('exchange')

    print("=" * 80)
    print("1. БІРЖІ, ДЕ НЕМАЄ ЖОДНОГО next_funding_utc")
    print("=" * 80)

    no_next_exchanges = []
    for exch, g in grouped:
        total = len(g)
        has_next_count = g['has_next'].sum()
        if has_next_count == 0:
            no_next_exchanges.append((exch, total))

    if not no_next_exchanges:
        print("Таких бірж не знайдено — у всіх є хоча б деякі наступні дати фандингу.")
    else:
        no_next_exchanges.sort(key=lambda x: x[1], reverse=True)
        for exch, cnt in no_next_exchanges:
            print(f"{exch:18} — {cnt:5} записів (0 з next_funding_utc)")

    print("\n" + "=" * 80)
    print("2. БІРЖІ, ДЕ Є ХОЧ ОДИН next_funding_utc")
    print("=" * 80)

    has_next_exchanges = []
    for exch, g in grouped:
        total = len(g)
        has_next_count = g['has_next'].sum()
        if has_next_count > 0:
            next_times = g.loc[g['has_next'], 'next_funding_dt']
            min_next = next_times.min().strftime('%Y-%m-%d %H:%M:%S UTC') if not next_times.empty else "—"
            max_next = next_times.max().strftime('%Y-%m-%d %H:%M:%S UTC') if not next_times.empty else "—"

            rates = g['funding_rate']
            min_rate = rates.min()
            max_rate = rates.max()

            has_next_exchanges.append((
                exch,
                total,
                has_next_count,
                min_next,
                max_next,
                min_rate,
                max_rate
            ))

    if not has_next_exchanges:
        print("Жодна біржа не має наступних дат фандингу.")
    else:
        has_next_exchanges.sort(key=lambda x: x[1], reverse=True)  # за кількістю записів
        print(f"{'Біржа':18} {'Всього':>6} {'З датою':>9} {'Мін next funding':>20} {'Макс next funding':>20} {'Мін rate':>10} {'Макс rate':>10}")
        print("-" * 110)
        for exch, total, has_cnt, min_n, max_n, min_r, max_r in has_next_exchanges:
            print(f"{exch:18} {total:6} {has_cnt:9} {min_n:>20} {max_n:>20} {min_r:10.6f} {max_r:10.6f}")

    # Загальна статистика
    total_records = len(df)
    total_with_next = df['has_next'].sum()
    print("\n" + "=" * 80)
    print(f"Загалом записів: {total_records}")
    print(f"З них з next_funding_utc: {total_with_next} ({total_with_next/total_records:.1%})")
    print("=" * 80)


if __name__ == "__main__":
    analyze_latest_funding_file()
    