import os
import asyncio
import sqlite3
from dotenv import load_dotenv
from collectors import YouTubeCollector, AsyncYouTubeCollector, QuotaManager, GoogleClientWrapper
from datetime import datetime, timedelta

import pandas as pd
pd.set_option('display.max_columns', None)

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
    "tier_0_ru",
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
print(len(search_list), search_list)
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


# ----------------------------
# Синхронний запуск
# ----------------------------
def run_sync():
    # ----------------------------
    # Ініціалізація Collector
    # ----------------------------
    collector = YouTubeCollector(api_wrapper, conn=conn)
    #collector.drop_tables(drop_search=False, drop_channels=True, drop_videos=True)
    #collector.vacuum()
    #return
    
    """
    rows = cursor.fetchall()
    cursor = conn.execute("SELECT * FROM channels_stats WHERE view_count > 2000000000")
    for row in rows:
        print(row)
    return
    """
    
    # ----------------------------
    # Пошук відео
    # ----------------------------
    #search_df = collector.search_videos(search_list, max_pages=1)
    #print("Search results:")
    #print(search_df)
    
    # дістаємо канали з пошуку
    cursor = conn.cursor()
    
    # Отримуємо унікальні video_id
    cursor.execute("SELECT DISTINCT video_id FROM search_videos")
    searched_videos = [row[0] for row in cursor.fetchall()]
    print("searched videos", len(searched_videos))
    
    # Отримуємо унікальні channel_id
    cursor.execute("SELECT DISTINCT channel_id FROM search_videos")
    searched_channels = [row[0] for row in cursor.fetchall()]
    print("searched channels", len(searched_channels))
  
    # ----------------------------
    # Отримання деталей каналів
    # ----------------------------
    channels_df = collector.get_channel_details(searched_channels)
    print("Channel details:")
    print(channels_df)
    return
    
    # ----------------------------
    # Отримання деталей відео
    # ----------------------------
    videos_df = collector.get_video_details(searched_videos)
    print("Video details:")
    print(videos_df)
    return
    
    # ----------------------------
    # Отримання останніх відео каналів (останні 90 днів)
    # ----------------------------
    latest_df = collector.get_channel_videos(
        channels_df.channel_id.tolist(),
        max_videos=100,
        until_date=datetime.utcnow() - timedelta(days=90)
    )
    print("Latest channel videos:")
    print(latest_df)
    
    # ----------------------------
    # Отримання останніх shorts каналів (останні 90 днів)
    # ----------------------------
    #latest_shorts_df = collector.get_channel_shorts(
    #    channels_df.channel_id.tolist(),
    #    max_videos=100,
    #    until_date=datetime.utcnow() - timedelta(days=90)
    #)
    #print("Latest channel short videos:")
    #print(latest_shorts_df)
    
    # ----------------------------
    # Отримання схожих відео
    # ----------------------------
    #related_df = collector.get_related_videos(videos_df.video_id.tolist()[:2], max_related=50)
    #print("Related videos:")
    #print(related_df)
    

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

