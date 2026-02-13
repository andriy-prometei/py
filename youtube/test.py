import os
import asyncio
import sqlite3
from dotenv import load_dotenv
from collectors import YouTubeCollector, AsyncYouTubeCollector, QuotaManager, GoogleClientWrapper
from datetime import datetime, timedelta
import pytz

import pandas as pd
pd.set_option('display.max_columns', None)

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "youtube-data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "data.db")

# Підключення до БД
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")  # дозволяє concurrent read
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA temp_store=MEMORY")
conn.execute("PRAGMA cache_size=-10000")  # ~10MB cache

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")

api_configs = [
    {"api_key": API_KEY},
    # {"api_key": "KEY2", "proxy": "http://user:pass@ip:port"}
]


target_keywords = {
    "tier_0_ru": [
        "crypto",
        "крипта",
    ],
    "tier_1_en": [
        "crypto arbitrage signals",
        "crypto funding rate signals",
        "crypto trading signals",
        "crypto signals telegram",
        "crypto arbitrage bot",
        "cross exchange arbitrage crypto",
        "funding rate arbitrage strategy",
        "how to use funding rate to profit",
        "crypto listing trading strategy",
        "crypto volatility trading strategy",
        "market neutral crypto strategies",
        "delta neutral crypto strategy",
        "basis trading crypto",
        "crypto cash and carry arbitrage",
        "crypto signals",
        "crypto futures trading strategy",
        "crypto arbitrage strategy", 
        "high leverage crypto strategy",
        "scalping crypto strategy", 
        "crypto day trading strategy",
        "perpetual futures crypto",
        "funding rate trading strategy",
        "funding rate arbitrage crypto strategy",
        "perpetual funding rate strategy",
        "best crypto signals service",
    ],
    "tier_1_ru": [
        "сигналы фандинга крипта",
        "телеграм сигналы крипта",
        "бот арбитраж криптовалют",
        "арбитраж крипты между биржами",
        "арбитраж фандинга крипта",
        "как заработать на фандинге",
        "арбитраж крипты обучение",
        "как торговать листинг криптовалют",
        "дельта нейтральная стратегия крипта",
        "базис трейдинг крипта",
        "cash and carry крипта",
        "крипто сигналы",
        "сигналы фьючерсы крипта",
        "арбитраж криптовалют",
        "скальпинг крипта",
        "фандинг крипта",
        "вилки крипта",
        "лучшие крипто сигналы",
        "межбиржевой арбитраж крипты",
    ],
    "tier_2_en": [
        "how to trade crypto profitably",
        "crypto trading bot", 
        "crypto passive income",
        "crypto trading strategies",
        "crypto arbitrage tutorial",
        "crypto funding rate explained",
        "how funding rate works crypto",
        "crypto arbitrage step by step",
        "how to find crypto arbitrage opportunities",
        "crypto trading automation",
        "crypto trading ai bot",
        "crypto market inefficiencies",
        "how market makers make money crypto",
    ],
    "tier_2_ru": [
        "как стабильно зарабатывать на крипте",
        "бот для торговли криптой", 
        "пассивный доход крипта",
        "как работает фандинг крипта",
        "как находить арбитраж криптовалют",
        "автоматическая торговля криптой",
        "рыночные неэффективности крипта",
        "как маркетмейкеры зарабатывают крипта",
    ],
    "tier_3_en": [
        "crypto listings strategy",
        "how to trade crypto listings",
        "crypto delisting signals",
        "how to trade new coin listings",
        "polymarket crypto strategy",
        "crypto prediction markets strategy",
        "how to predict crypto price ranges",
    ],
    "tier_3_ru": [
        "сигналы листинга крипта",
        "делистинг криптовалют как заработать",
        "стратегия полимаркет крипта",
        "рынки предсказаний крипта",
        "как предсказывать диапазон цены крипты",
        "торговля волатильностью крипта",
    ],
}

selected_tiers = [
    #"tier_0_ru",
    #"tier_1_ru",
    #"tier_1_en",
    #"tier_2_ru",
    #"tier_2_en",
    #"tier_3_ru",
    #"tier_3_en",
]

search_list = []
unique_keys = []
for tkey in selected_tiers:
    langs = [""]
    regions = [""]
    lang_suffix = tkey.split("_")[-1]
    if lang_suffix == "en":
        #langs = ["", "en"]
        #regions = ["", "US", "GB", "CA", "AU"]
        pass
    elif lang_suffix == "ru":
        #langs = ["", "ru"]
        #regions = ["", "UA", "KZ", "RU", "BY"]
        pass
    
    for kw in target_keywords[tkey]:
        if kw in unique_keys:
          continue
        unique_keys.append(kw)
        
        for lang in langs:
            for region in regions:
                search_list.append({
                    "keyword": kw,
                    "language": lang,
                    "region": region,
                })
#print(len(search_list), search_list)
#exit()


# ----------------------------
# Ініціалізація QuotaManager
# ----------------------------
quota_manager = QuotaManager(
    quota_file=os.path.join(DATA_DIR, "quota.json"),
    log_file=os.path.join(DATA_DIR, "api_calls.log")
)

# ----------------------------
# Ініціалізація обгортки API
# ----------------------------
api_wrapper = GoogleClientWrapper(
    api_configs=api_configs,
    quota_manager=quota_manager,
    caller_tag="test",
    purpose_tag="init",
    requests_per_second=5  # можна змінити
)

def is_daily_window():
    pac_time_str = datetime.utcnow().astimezone(pytz.timezone("US/Pacific")).strftime("%H:%M:%S")
    return (pac_time_str > "00:04") and (pac_time_str < "02:56")
    

def run_sync__():
    collector = YouTubeCollector(api_wrapper, conn=conn)
    cursor = conn.cursor()
    
    
    #collector.drop_tables(drop_search=False, drop_channels=True, drop_videos=True)
    #collector.vacuum()
    #return
    

    # =====================================================
    # STEP 1 — SEARCH NEW VIDEOS
    # =====================================================
    try:
        if search_list:
            print("STEP 1: search videos")
            search_df = collector.search_videos(search_list, max_pages=1)
    except Exception as e:
        print("STEP 1 ERROR:", e)

    # =====================================================
    # STEP 2 — DAILY CHANNEL REFRESH
    # =====================================================
    try:
        if is_daily_window():
            print("STEP 2: daily channel refresh")

            cursor.execute("""
                SELECT channel_id
                FROM channels_main
                WHERE scraped_at < DATETIME('now', 'start of day')
            """)
            stale_channels = [r[0] for r in cursor.fetchall()]

            cursor.execute("""
                SELECT DISTINCT channel_id
                FROM search_videos
                WHERE scraped_at >= DATETIME('now', 'start of day')
            """)
            fresh_channels = [r[0] for r in cursor.fetchall()]

            channels = list(set(stale_channels + fresh_channels))
            print("Channels to refresh:", len(channels))

            if channels:
                collector.get_channel_details(channels)
                new_video_ids = collector.get_channel_videos(channels)
                collected_video_ids.update(new_video_ids)

    except Exception as e:
        print("STEP 2 ERROR:", e)

    # =====================================================
    # STEP 3 — HOURLY VIDEO STATS REFRESH
    # =====================================================
    try:
        print("STEP 3: refresh video stats")
        cursor.execute("""
            SELECT DISTINCT video_id
            FROM videos_main
            WHERE published_at >= DATETIME('now', '-7 day')
        """)
        fresh_videos = {r[0] for r in cursor.fetchall()}

        video_ids = list(fresh_videos | collected_video_ids)
        print("Videos to refresh:", len(video_ids))

        if video_ids:
            collector.get_video_details(video_ids)

    except Exception as e:
        print("STEP 3 ERROR:", e)
        
        
clear_db = False

search_new_videos = False
fill_channel_details = True

get_last_channel_videos = True

get_video_details = True
get_video_details_ids = []

# ----------------------------
# Синхронний запуск
# ----------------------------
def run_sync():
    # ----------------------------
    # Ініціалізація Collector
    # ----------------------------
    collector = YouTubeCollector(api_wrapper, conn=conn)
    cursor = conn.cursor()
    
    if clear_db:
        print("STEP 0: clear db")
        collector.drop_tables(drop_search=False, drop_channels=True, drop_videos=True)
        collector.vacuum()
        print("STEP 0: done")
        return
    
    if search_new_videos and search_list:
        print("STEP 1: search videos")
        try:
            search_df = collector.search_videos(search_list, max_pages=1)
            print("Search results added:")
            print(search_df)
        except Exception as e:
            print("STEP 1 ERROR:", e)
    
    if fill_channel_details:
        print("STEP 2: fill channel details")
        try:
            # Отримуємо унікальні channel_id з пошуку
            cursor.execute("SELECT DISTINCT channel_id FROM search_videos")
            searched_channels = [row[0] for row in cursor.fetchall()]
            
            # Отримуємо унікальні channel_id з каналів
            cursor.execute("SELECT channel_id FROM channels_main")
            stale_channels = [r[0] for r in cursor.fetchall()]
            
            collect_channels = list(set(searched_channels) - set(stale_channels))
            if collect_channels:
                channels_cnt = collector.get_channel_details(collect_channels)
                print("Channel details added:", channels_cnt)
        except Exception as e:
            print("STEP 2 ERROR:", e)

    if get_last_channel_videos:
        print("STEP 3: get last channel videos")
        try:
            cursor.execute("SELECT channel_id FROM channels_main WHERE last_published_at='' LIMIT 5")
            fresh_channels = [r[0] for r in cursor.fetchall()]
            if fresh_channels:
                all_video_ids = collector.get_channel_videos(
                    fresh_channels,
                    max_videos=5,
                    until_date=datetime.utcnow() - timedelta(days=90)
                )
                get_video_details_ids.extend(all_video_ids)
                print("Latest channel videos:", len(all_video_ids))
        except Exception as e:
            print("STEP 3 ERROR:", e)
    
    if get_video_details and get_video_details_ids:
        print("STEP 4: get video details")
        try:
            videos_df = collector.get_video_details(get_video_details_ids)
            print("Video details:")
            print(videos_df)
        except Exception as e:
            print("STEP 4 ERROR:", e)


if __name__ == "__main__":
        # ----------------------------
    # Вивід поточного стану квоти
    # ----------------------------
    for key in [c["api_key"] for c in api_configs]:
        status = quota_manager.get_status(key)
        print(f"Quota {key}: {status}")
    
    run_sync()         # синхронний
    #asyncio.run(run_async())  # Асинхронний
    
    # ----------------------------
    # Кінцевий стан квоти
    # ----------------------------
    for key in [c["api_key"] for c in api_configs]:
        status = quota_manager.get_status(key)
        print(f"Final quota status for {key}: {status}")


"""
# via  proxy
from googleapiclient.discovery import build
from googleapiclient.http import HttpRequest
import httplib2

proxy_info = httplib2.ProxyInfo(
    proxy_type=httplib2.socks.PROXY_TYPE_HTTP,
    proxy_host='127.0.0.1',
    proxy_port=8080
)
http = httplib2.Http(proxy_info=proxy_info)

youtube = build("youtube", "v3", developerKey=API_KEY, http=http)
"""

