import sqlite3
import pandas as pd
from datetime import datetime
import threading
import isodate

class YouTubeCollector:
    def __init__(self, api_wrapper, db_path=None, conn=None):
        self.api = api_wrapper
        self.lock = threading.Lock()
        
        if conn:
            self.conn = conn
            self.own_conn = False
        elif db_path:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.own_conn = True
        else:
            raise ValueError("Потрібно вказати db_path або conn")
        
        self._init_tables()

    # ====================================================
    # HELPERS
    # ====================================================
    @staticmethod
    def _format_time(iso_str):
        """Перетворює ISO у формат YYYY-MM-DD HH:MM:SS"""
        if not iso_str:
            return ''
        iso_str = iso_str.rstrip('Z')
        try:
            dt = datetime.fromisoformat(iso_str)
        except ValueError:
            dt = datetime.strptime(iso_str.split(".")[0], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
        
    def _to_int(self, v, default=-1):
        if v is None:
            return default
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v)
            except:
                return default
        return default

    def _utc_now(self):
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    def _batch(self, items, size=50):
        for i in range(0, len(items), size):
            yield items[i:i+size]

    def _prepare_row(self, row):
        """Заповнює None дефолтами"""
        for k, v in row.items():
            if v is None:
                if "count" in k:
                    row[k] = -1
                else:
                    row[k] = ''
        return row
    
    def _bulk_upsert(self, table, rows, cols, conflict_cols=None, batch_size=500):
        """
        table: назва таблиці
        rows: список кортежів
        cols: список колонок для вставки
        conflict_cols: список колонок для ON CONFLICT (None → просто вставка)
        """
        if not rows:
            return
    
        placeholders = ", ".join("?" for _ in cols)
        columns_str = ", ".join(cols)
    
        if conflict_cols:
            conflict_str = ", ".join(conflict_cols)
            # Для main: оновлюємо scraped_at
            update_set = ", ".join([f"{c}=excluded.{c}" for c in cols if c not in conflict_cols])
            sql = f"""
                INSERT INTO {table} ({columns_str})
                VALUES ({placeholders})
                ON CONFLICT({conflict_str}) DO UPDATE SET {update_set}
            """
        else:
            # Для snippet (INSERT OR IGNORE) або stats (просто вставка)
            sql = f"INSERT OR IGNORE INTO {table} ({columns_str}) VALUES ({placeholders})"
    
        with self.lock:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i+batch_size]
                self.conn.executemany(sql, batch)
            self.conn.commit()
    
    def _upsert_df(self, df, table, pk_cols=None):
        """Вставка масиву даних у БД"""
        if df.empty:
            return
        cols = df.columns.tolist()
        placeholders = ", ".join("?" for _ in cols)
        data = [tuple(x) for x in df.to_numpy()]

        with self.lock:
            if pk_cols:
                updates = ", ".join([f"{c}=excluded.{c}" for c in cols if c not in pk_cols])
                sql = f"""
                INSERT INTO {table} ({', '.join(cols)})
                VALUES ({placeholders})
                ON CONFLICT({', '.join(pk_cols)}) DO UPDATE SET {updates}
                """
                self.conn.executemany(sql, data)
            else:
                sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
                self.conn.executemany(sql, data)
            self.conn.commit()

    # ====================================================
    # INIT TABLES
    # ====================================================
    def _init_tables(self):
        with self.conn:
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS search_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL DEFAULT '',
                src_video_id TEXT NOT NULL DEFAULT '',
                keyword TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT '',
                channel_id TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT -1,
                scraped_at TEXT NOT NULL DEFAULT ''
            )""")
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS channels_main (
                channel_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT '',
                firstly_scraped_at TEXT NOT NULL DEFAULT '',
                scraped_at TEXT NOT NULL DEFAULT '',
                uploads_playlist TEXT NOT NULL DEFAULT '',
                last_published_at TEXT NOT NULL DEFAULT ''
            )""")
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS channels_snippet (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL DEFAULT '',
                scraped_at TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT ''
            )""")
            self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_snippet_unique
                ON channels_snippet(channel_id, title, description)
            """)
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS channels_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL DEFAULT '',
                scraped_at TEXT NOT NULL DEFAULT '',
                video_count INTEGER NOT NULL DEFAULT -1,
                subscriber_count INTEGER NOT NULL DEFAULT -1,
                view_count INTEGER NOT NULL DEFAULT -1
            )""")
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS videos_main (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                scraped_at TEXT NOT NULL DEFAULT '',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                is_short INTEGER NOT NULL DEFAULT 0
            )""")
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS videos_snippet (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL DEFAULT '',
                scraped_at TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT ''
            )""")
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS videos_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL DEFAULT '',
                scraped_at TEXT NOT NULL DEFAULT '',
                view_count INTEGER NOT NULL DEFAULT -1,
                like_count INTEGER NOT NULL DEFAULT -1,
                comment_count INTEGER NOT NULL DEFAULT -1
            )""")
            
    def drop_tables(self, drop_search=False, drop_channels=False, drop_videos=False):
      
        tables = []
        if drop_search:
            tables.extend([
                "search_videos"
            ])
        if drop_channels:
            tables.extend([
                "channels_main",
                "channels_snippet",
                "channels_stats"
            ])
        if drop_videos:
            tables.extend([
                "videos_main",
                "videos_snippet",
                "videos_stats"
            ])
        if not tables:
            return  # нічого не дропати
    
        with self.conn:
            for table in tables:
                self.conn.execute(f"DROP TABLE IF EXISTS {table}")
    
    def vacuum(self):
        with self.conn:
            self.conn.execute("PRAGMA optimize")
        # VACUUM не можна запускати всередині транзакції
        self.conn.commit()
        self.conn.execute("VACUUM")
        
    def backup_db(self, backup_path):
        with sqlite3.connect(backup_path) as backup_conn:
            self.conn.backup(backup_conn)

    # ====================================================
    # SEARCH VIDEOS
    # ====================================================
    def search_videos(self, search_requests, max_pages=1):
        rows = []

        for req in search_requests:
            keyword = req.get("keyword", '')
            lang = req.get("language", '')
            region = req.get("region", '')
            position = 0

            token = None
            for _ in range(max_pages):
                params = {
                    "q": keyword,
                    "part": "id,snippet",
                    "type": "video",
                    "maxResults": 50,
                    "pageToken": token
                }
                if lang: params["relevanceLanguage"] = lang
                if region: params["regionCode"] = region

                response = self.api.execute(
                    lambda client, **p: client.search().list(**p),
                    "search.list",
                    params
                )

                for item in response.get("items", []):
                    position += 1
                    row = {
                        "video_id": item["id"]["videoId"],
                        "src_video_id": '',
                        "keyword": keyword,
                        "language": lang,
                        "region": region,
                        "channel_id": item["snippet"].get("channelId", ''),
                        "position": position,
                        "scraped_at": self._utc_now()
                    }
                    rows.append(self._prepare_row(row))

                token = response.get("nextPageToken")
                if not token:
                    break

        df = pd.DataFrame(rows)
        self._upsert_df(df, "search_videos")
        return df

    # ====================================================
    # GET CHANNEL DETAILS
    # ====================================================
    def get_channel_details(self, channel_ids):
        now = self._utc_now()
        rows_main, rows_snippet, rows_stats = [], [], []
    
        for batch_ids in self._batch(channel_ids):
            params = {"part": "snippet,statistics,contentDetails", "id": ",".join(batch_ids)}
            response = self.api.execute(
                lambda client, **p: client.channels().list(**p),
                "channels.list",
                params
            )
    
            for item in response.get("items", []):
                stats = item.get("statistics", {})
                snippet = item.get("snippet", {})
                content = item.get("contentDetails", {}).get("relatedPlaylists", {})
    
                # ---------------- MAIN ----------------
                row_main = (
                    item["id"],
                    self._format_time(snippet.get("publishedAt")),
                    now,  # firstly_scraped_at
                    now,  # scraped_at
                    content.get("uploads", ''),
                    ''
                )
                rows_main.append(row_main)
    
                # ---------------- SNIPPET ----------------
                row_snippet = (
                    item["id"],
                    now,
                    snippet.get("title", ''),
                    snippet.get("description", '')
                )
                rows_snippet.append(row_snippet)
    
                # ---------------- STATS ----------------
                row_stats = (
                    item["id"],
                    now,
                    self._to_int(stats.get("videoCount", -1)),
                    self._to_int(stats.get("subscriberCount", -1)),
                    self._to_int(stats.get("viewCount", -1))
                )
                rows_stats.append(row_stats)
    
        # ---------------- UPSERT / INSERT ----------------
        if rows_main:
            self._bulk_upsert(
                "channels_main",
                rows_main,
                cols=["channel_id", "created_at", "firstly_scraped_at", "scraped_at", "uploads_playlist", "last_published_at"],
                conflict_cols=["channel_id"]
            )
        if False
            with self.lock:
                self.conn.executemany("""
                    INSERT INTO channels_main(
                        channel_id, created_at, firstly_scraped_at, scraped_at,
                        uploads_playlist, last_published_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET
                        scraped_at = excluded.scraped_at
                """, rows_main)
                self.conn.commit()
    
        if rows_snippet:
            self._bulk_upsert(
                "channels_snippet",
                rows_snippet,
                cols=["channel_id", "scraped_at", "title", "description"]
                # conflict_cols=None → INSERT OR IGNORE
            )
    
        if rows_stats:
            self._bulk_upsert(
                "channels_stats",
                rows_stats,
                cols=["channel_id", "scraped_at", "video_count", "subscriber_count", "view_count"]
                # conflict_cols=None → INSERT OR IGNORE
            )
    
        return len(rows_main)

    # ====================================================
    # GET VIDEO DETAILS
    # ====================================================
    def get_video_details(self, video_ids):
        rows_main, rows_snippet, rows_stats = [], [], []

        # --- витягуємо існуючі is_short щоб не перезаписати 5 ---
        existing_flags = {}
        if video_ids:
            placeholders = ",".join("?" for _ in video_ids)
            query = f"""
                SELECT video_id, is_short 
                FROM videos_main 
                WHERE video_id IN ({placeholders})
            """
            cur = self.conn.execute(query, list(video_ids))
            existing_flags = dict(cur.fetchall())

        for batch_ids in self._batch(video_ids):
            params = {"part": "snippet,statistics,contentDetails", "id": ",".join(batch_ids)}
            response = self.api.execute(lambda client, **p: client.videos().list(**p),
                                        "videos.list", params)

            now = self._utc_now()

            for item in response.get("items", []):
                vid = item["id"]

                duration = int(round(
                    isodate.parse_duration(item["contentDetails"]["duration"]).total_seconds()
                ))

                # --- логіка захисту прапора Shorts ---
                if existing_flags.get(vid) == 5:
                    is_short = 5
                else:
                    is_short = 1 if 0 < duration <= 60 else 0

                row_main = {
                    "video_id": vid,
                    "channel_id": item["snippet"].get("channelId", ''),
                    "published_at": self._format_time(item["snippet"].get("publishedAt")),
                    "scraped_at": now,
                    "duration_seconds": duration,
                    "is_short": is_short
                }

                row_snippet = {
                    "video_id": vid,
                    "scraped_at": now,
                    "title": item["snippet"].get("title", ''),
                    "description": item["snippet"].get("description", ''),
                    "tags": ','.join(item["snippet"].get("tags", []))
                }

                row_stats = {
                    "video_id": vid,
                    "scraped_at": now,
                    "view_count": item["statistics"].get("viewCount", -1),
                    "like_count": item["statistics"].get("likeCount", -1),
                    "comment_count": item["statistics"].get("commentCount", -1)
                }

                rows_main.append(self._prepare_row(row_main))
                rows_snippet.append(self._prepare_row(row_snippet))
                rows_stats.append(self._prepare_row(row_stats))

        df_main = pd.DataFrame(rows_main)
        df_snippet = pd.DataFrame(rows_snippet)
        df_stats = pd.DataFrame(rows_stats)

        self._upsert_df(df_main, "videos_main", ["video_id"])
        self._upsert_df(df_snippet, "videos_snippet")
        self._upsert_df(df_stats, "videos_stats")

        return df_main
        
    # ====================================================
    # GE0 CHANNEL VIDEOS VIA UPLOADS PLAYLIST
    # ====================================================
    def get_channel_videos(self, channel_ids, max_videos=200, until_date=None):
        channel_df = self.get_channel_details(channel_ids)
        all_video_ids = []
    
        for _, row in channel_df.iterrows():
            channel_id = row["channel_id"]
            playlist = row["uploads_playlist"]
    
            with self.conn:
                res = self.conn.execute(
                    "SELECT last_published_at FROM channels_main WHERE channel_id=?",
                    (channel_id,)
                ).fetchone()
            last_pub = res[0] if res else None
            stop_date = datetime.fromisoformat(last_pub) if last_pub else until_date
    
            token = None
            collected = 0
            while True:
                params = {
                    "part": "snippet",
                    "playlistId": playlist,
                    "maxResults": 50,
                    "pageToken": token
                }
                response = self.api.execute(
                    lambda client, **p: client.playlistItems().list(**p),
                    "playlistItems.list",
                    params
                )
    
                for item in response.get("items", []):
                    pub_str = item["snippet"]["publishedAt"].replace("Z", "")
                    pub_dt = datetime.fromisoformat(pub_str.split(".")[0])
                    if stop_date and pub_dt <= stop_date:
                        continue
                    vid_id = item["snippet"]["resourceId"]["videoId"]
                    all_video_ids.append(vid_id)
                    collected += 1
                    if collected >= max_videos:
                        break
    
                token = response.get("nextPageToken")
                if not token or collected >= max_videos:
                    break
    
        videos_df = self.get_video_details(all_video_ids)
    
        # Оновлюємо last_published_at
        for channel_id in channel_ids:
            ch_videos = videos_df[videos_df["channel_id"] == channel_id]
            if not ch_videos.empty:
                max_pub = ch_videos["published_at"].max()
                self.conn.execute(
                    "UPDATE channels_main SET last_published_at=? WHERE channel_id=?",
                    (max_pub, channel_id)
                )
        self.conn.commit()
        return videos_df
    
    # ====================================================
    # GET RELATED VIDEOS
    # ====================================================
    def get_related_videos(self, video_ids, max_related=50):
        rows = []

        for src_vid in video_ids:
            token = None
            collected = 0
            position = 0

            while True:
                params = {
                    "part": "id,snippet",   # <-- FIX
                    "relatedToVideoId": src_vid,
                    "type": "video",
                    "maxResults": 50,
                    "pageToken": token
                }

                response = self.api.execute(
                    lambda client, **p: client.search().list(**p),
                    "search.list",
                    params
                )

                for item in response.get("items", []):
                    position += 1

                    related_vid = item["id"]["videoId"]

                    row = {
                        "video_id": related_vid,
                        "src_video_id": src_vid,
                        "keyword": '',
                        "language": '',
                        "region": '',
                        "channel_id": item["snippet"].get("channelId", ''),
                        "position": position,
                        "scraped_at": self._utc_now()
                    }

                    rows.append(self._prepare_row(row))
                    collected += 1

                    if collected >= max_related:
                        break

                token = response.get("nextPageToken")
                if not token or collected >= max_related:
                    break

        df = pd.DataFrame(rows)
        self._upsert_df(df, "search_videos")
        return df
    
# ====================================================
    # GET CHANNEL SHORTS VIA SHORTS PLAYLIST (UUSH...)
    # Працює як get_channel_videos + захист від 404
    # ====================================================
    def get_channel_shorts(self, channel_ids, max_videos=200, until_date=None):
        from googleapiclient.errors import HttpError

        all_video_ids = []

        for channel_id in channel_ids:
            shorts_playlist = "UUSH" + channel_id[2:]

            with self.conn:
                res = self.conn.execute(
                    "SELECT last_published_at FROM channels_main WHERE channel_id=?",
                    (channel_id,)
                ).fetchone()

            last_pub = res[0] if res else None
            stop_date = datetime.fromisoformat(last_pub) if last_pub else until_date

            token = None
            collected = 0

            while True:
                params = {
                    "part": "snippet",
                    "playlistId": shorts_playlist,
                    "maxResults": 50,
                    "pageToken": token
                }

                try:
                    response = self.api.execute(
                        lambda client, **p: client.playlistItems().list(**p),
                        "playlistItems.list",
                        params
                    )

                # ---- Playlist може не існувати ----
                except HttpError as e:
                    if e.resp.status == 404:
                        break
                    raise

                for item in response.get("items", []):
                    pub_str = item["snippet"]["publishedAt"].replace("Z", "")
                    pub_dt = datetime.fromisoformat(pub_str.split(".")[0])

                    if stop_date and pub_dt <= stop_date:
                        continue

                    vid_id = item["snippet"]["resourceId"]["videoId"]
                    all_video_ids.append(vid_id)
                    collected += 1

                    if collected >= max_videos:
                        break

                token = response.get("nextPageToken")
                if not token or collected >= max_videos:
                    break

        if not all_video_ids:
            return pd.DataFrame()

        videos_df = self.get_video_details(all_video_ids)

        # Примусово виставляємо прапор Shorts = 5
        if not videos_df.empty:
            videos_df["is_short"] = 5
            self._upsert_df(videos_df, "videos_main", ["video_id"])

        # Оновлюємо last_published_at
        for channel_id in channel_ids:
            ch_videos = videos_df[videos_df["channel_id"] == channel_id]
            if not ch_videos.empty:
                max_pub = ch_videos["published_at"].max()
                self.conn.execute(
                    "UPDATE channels_main SET last_published_at=? WHERE channel_id=?",
                    (max_pub, channel_id)
                )

        self.conn.commit()
        return videos_df
        