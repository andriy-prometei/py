import pandas as pd
import glob
from pathlib import Path
import re 

# ==================== КОНФІГУРАЦІЯ ====================
DATA_DIR = Path("gdelt_data")
FILE_PATTERN = "*.gkg.csv" 
THEMES_OUTPUT_FILE = "themes_frequency.txt"
PERSONS_OUTPUT_FILE = "persons_frequency.txt"

CRYPTO_KEYWORDS = [
    "BITCOIN", "ETHEREUM", "CRYPTOCURRENCY", "BLOCKCHAIN", 
    "BTC", "DOGECOIN", "BINANCE", "COINBASE", "CRYPTO", "SOLANA", "NFT"
]

# Регулярний вираз для фільтрації коротких кодів (якщо вони все ж потраплять)
CODE_PATTERN = re.compile(r'^\w+\d+$')

# =======================================================

def load_gkg_file(filepath):
    """
    Завантажує GDELT GKG файл.
    !!! Змінено індекс для Persons на 16 (V2Persons) !!!
    """
    # Індекси колонок GDELT:
    # 1: Date | 3: SourceCommonName | 4: URL | 7: V2Themes | 15: V2.1Tone | 16: V2Persons
    
    col_indices = [1, 3, 4, 7, 15, 16]
    col_names = ['Date', 'Source', 'URL', 'Themes', 'ToneData', 'Persons']

    try:
        df = pd.read_csv(
            filepath, 
            sep='\t',            
            header=None,         
            names=col_names,     
            usecols=col_indices, 
            encoding='utf-8',    
            on_bad_lines='skip', 
            dtype={
                'Date': str, 'Source': str, 'URL': str, 
                'Themes': str, 'ToneData': str, 'Persons': str
            }
        )
        df = df.dropna(subset=['URL', 'Themes', 'ToneData'])
        return df
    except Exception as e:
        print(f"Помилка читання {filepath.name}: {e}")
        return pd.DataFrame()

def parse_tone(tone_str):
    """Витягує перше значення (AvgTone) зі стовпця ToneData."""
    try:
        if pd.isna(tone_str):
            return 0.0
        return float(str(tone_str).split(',')[0])
    except:
        return 0.0

def calculate_frequency(df_column, separator, output_filename, is_person=False):
    """Розраховує частоту елементів та зберігає результат."""
    if df_column.empty:
        print(f"Дані для {output_filename} відсутні.")
        return

    elements_series = df_column.dropna().astype(str).str.split(separator).explode()
    
    # 1. Видаляємо зайві пробіли та порожні рядки
    elements_series = elements_series.str.strip().replace('', pd.NA).dropna()
    
    # 2. Фільтрація для персон
    if is_person:
        initial_count = len(elements_series)
        # Видаляємо короткі коди, які не схожі на імена (наприклад, "Biden" пройде, "C12.4" - ні)
        elements_series = elements_series[~elements_series.apply(lambda x: bool(CODE_PATTERN.match(x)))]
        # Залишаємо лише ті, що містять принаймні один пробіл (ім'я та прізвище)
        elements_series = elements_series[elements_series.str.contains(r'\s', na=False)]
        
        filtered_count = len(elements_series)
        print(f"   --> Відфільтровано: {initial_count - filtered_count} не-імен/кодів.")
    
    # 3. Рахуємо частоту
    frequency = elements_series.value_counts()
    
    # Зберігаємо у файл
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write("Елемент\tЧастота\n")
        frequency.to_csv(f, sep='\t', header=False)
        
    print(f"✅ Успішно збережено {len(frequency)} унікальних елементів у {output_filename}")


def analyze_crypto(df):
    """Фільтрує новини по крипті та рахує статистику."""
    df['Sentiment'] = df['ToneData'].apply(parse_tone)
    pattern = '|'.join(CRYPTO_KEYWORDS)
    crypto_df = df[df['Themes'].str.contains(pattern, case=False, na=False)].copy()
    return crypto_df

def main():
    try:
        import pandas as pd
    except ImportError:
        print("\nПомилка: Бібліотека 'pandas' не знайдена. Встановіть її командою: pip install pandas")
        return
        
    files = list(DATA_DIR.glob(FILE_PATTERN))
    if not files:
        print(f"Файлів GKG не знайдено в {DATA_DIR}.")
        return

    files.sort()
    latest_file = files[-1] 
    
    print(f"Аналіз файлу: {latest_file.name}")

    df = load_gkg_file(latest_file)
    
    if df.empty:
        print("Файл порожній або побитий. Вихід.")
        return

    # ==================== РОЗРАХУНОК ТА ЗБЕРЕЖЕННЯ ====================

    # 1. ТЕМИ (Themes)
    print("\n--- Обробка ТЕМ ---")
    calculate_frequency(df['Themes'], ';', THEMES_OUTPUT_FILE, is_person=False)

    # 2. ПЕРСОНИ (Persons) - ВИКОРИСТОВУЄМО КОЛОНКУ 16
    print("\n--- Обробка ПЕРСОН (ОЧИЩЕННЯ) ---")
    calculate_frequency(df['Persons'], ';', PERSONS_OUTPUT_FILE, is_person=True)
    
    # ==================== АНАЛІЗ СЕНТИМЕНТУ (Демонстрація) ====================
    crypto_df = analyze_crypto(df)
    
    # ... (решта коду аналізу сентименту залишена без змін для цілей демонстрації)
    print(f"\n========================================")
    print(f"📊 АНАЛІЗ КРИПТО-НОВИН")
    print(f"========================================")
    
    count = len(crypto_df)
    print(f"Кількість новин, що згадують: {count}")
    
    if count > 0:
        avg_sentiment = crypto_df['Sentiment'].mean()
        mood = "😐 Нейтрально"
        if avg_sentiment > 1: mood = "🙂 Позитивно"
        if avg_sentiment < -1: mood = "🙁 Негативно"
        
        print(f"Середній сентимент: {avg_sentiment:.4f}")
        print(f"Настрій ринку: {mood}")

        print("\n--- ТОП ПЕРСОН, ПОВ'ЯЗАНИХ ІЗ КРИПТОЮ (ОЧИЩЕНО) ---")
        person_series = crypto_df['Persons'].dropna().astype(str).str.split(';').explode().str.strip()
        
        # Застосовуємо очистку до серії для відображення
        person_series = person_series[~person_series.apply(lambda x: bool(CODE_PATTERN.match(x)))]
        person_series = person_series[person_series.str.contains(r'\s', na=False)]
        
        if not person_series.empty:
             print(person_series.value_counts().head(5).to_string())
        else:
            print("Не знайдено чистих імен, пов'язаних із криптою.")
    else:
        print("У цьому 15-хвилинному інтервалі новин за ключовими словами не знайдено.")

if __name__ == "__main__":
    main()
