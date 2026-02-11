import asyncio
import aiohttp
import pandas as pd
from datetime import datetime
from datetime import timedelta
import isodate


class AsyncYouTubeCollector:

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    DAILY_QUOTA_LIMIT = 10000

    COSTS = {
        "search": 100,
        "videos": 1,
        "channels": 1,
        "playlistItems": 1
    }

    def __init__(self, api_key, rps=8, max_connections=20):

        self.api_key = api_key

        self.semaphore = asyncio.Semaphore(max_connections)
        self.rps = rps

        self.used_quota = 0
        self.soft_wait_until = None

        self.last_request = 0

    # =====================================================
    # THROTTLE
    # =====================================================
    async def _throttle(self):

        now = asyncio.get_event_loop().time()

        if self.soft_wait_until and now < self.soft_wait_until:
            await asyncio.sleep(self.soft_wait_until - now)

        delta = now - self.last_request
        min_interval = 1 / self.rps

        if delta < min_interval:
            await asyncio.sleep(min_interval - delta)

        self.last_request = asyncio.get_event_loop().time()

    # =====================================================
    # REQUEST
    # =====================================================
    async def _request(self, session, endpoint, params, cost):

        params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(5):

            await self._throttle()

            async with self.semaphore:
                async with session.get(url, params=params) as resp:

                    if resp.status == 403:
                        text = await resp.text()

                        if "quotaExceeded" in text:
                            raise RuntimeError("Quota exceeded")

                        if "userRateLimitExceeded" in text:
                            wait = 60 * (attempt + 1)
                            self.soft_wait_until = asyncio.get_event_loop().time() + wait
                            await asyncio.sleep(wait)
                            continue

                    resp.raise_for_status()
                    data = await resp.json()

                    self.used_quota += cost
                    return data

        raise RuntimeError("Max retries reached")

    # =====================================================
    # BATCH
    # =====================================================
    @staticmethod
    def _batch(items, size=50):
        for i in range(0, len(items), size):
            yield items[i:i + size]

    # =====================================================
    # SEARCH
    # =====================================================
    async def search_videos(self, search_requests, max_pages=1):

        rows = []

        async with aiohttp.ClientSession() as session:

            for req in search_requests:

                token = None
                position = 0

                for _ in range(max_pages):

                    params = {
                        "q": req["keyword"],
                        "part": "id,snippet",
                        "type": "video",
                        "maxResults": 50,
                        "pageToken": token
                    }

                    if req.get("language"):
                        params["relevanceLanguage"] = req["language"]

                    if req.get("region"):
                        params["regionCode"] = req["region"]

                    data = await self._request(
                        session, "search", params, self.COSTS["search"]
                    )

                    for item in data.get("items", []):
                        position += 1

                        rows.append({
                            "keyword": req["keyword"],
                            "language": req.get("language"),
                            "region": req.get("region"),
                            "video_id": item["id"]["videoId"],
                            "channel_id": item["snippet"]["channelId"],
                            "position": position,
                            "scraped_at": datetime.utcnow().isoformat()
                        })

                    token = data.get("nextPageToken")
                    if not token:
                        break

        return pd.DataFrame(rows)

    # =====================================================
    # VIDEO DETAILS
    # =====================================================
    async def get_video_details(self, video_ids):

        rows = []

        async with aiohttp.ClientSession() as session:

            tasks = []

            for ids in self._batch(video_ids):

                params = {
                    "id": ",".join(ids),
                    "part": "snippet,statistics,contentDetails"
                }

                tasks.append(
                    self._request(session, "videos", params, self.COSTS["videos"])
                )

            responses = await asyncio.gather(*tasks)

            for data in responses:

                for item in data.get("items", []):

                    duration = item["contentDetails"]["duration"]
                    seconds = isodate.parse_duration(duration).total_seconds()

                    rows.append({
                        "video_id": item["id"],
                        "channel_id": item["snippet"]["channelId"],
                        "title": item["snippet"]["title"],
                        "description": item["snippet"]["description"],
                        "published_at": item["snippet"]["publishedAt"],
                        "view_count": item["statistics"].get("viewCount"),
                        "like_count": item["statistics"].get("likeCount"),
                        "comment_count": item["statistics"].get("commentCount"),
                        "duration": duration,
                        "is_short": seconds <= 60
                    })

        return pd.DataFrame(rows)

    # =====================================================
    # CHANNEL DETAILS
    # =====================================================
    async def get_channel_details(self, channel_ids):

        rows = []

        async with aiohttp.ClientSession() as session:

            tasks = []

            for ids in self._batch(channel_ids):

                params = {
                    "id": ",".join(ids),
                    "part": "snippet,statistics,contentDetails"
                }

                tasks.append(
                    self._request(session, "channels", params, self.COSTS["channels"])
                )

            responses = await asyncio.gather(*tasks)

            for data in responses:

                for item in data.get("items", []):

                    rows.append({
                        "channel_id": item["id"],
                        "title": item["snippet"]["title"],
                        "description": item["snippet"]["description"],
                        "created_at": item["snippet"]["publishedAt"],
                        "uploads_playlist":
                            item["contentDetails"]["relatedPlaylists"]["uploads"]
                    })

        return pd.DataFrame(rows)

    # =====================================================
    # CHANNEL VIDEOS
    # =====================================================
    async def get_channel_videos(self, channel_ids, max_videos=200, until_date=None):

        channel_df = await self.get_channel_details(channel_ids)

        video_ids = []

        async with aiohttp.ClientSession() as session:

            for _, row in channel_df.iterrows():

                playlist = row["uploads_playlist"]
                token = None
                collected = 0

                while True:

                    params = {
                        "playlistId": playlist,
                        "part": "snippet",
                        "maxResults": 50,
                        "pageToken": token
                    }

                    data = await self._request(
                        session,
                        "playlistItems",
                        params,
                        self.COSTS["playlistItems"]
                    )

                    for item in data.get("items", []):

                        pub = datetime.fromisoformat(
                            item["snippet"]["publishedAt"].replace("Z", "")
                        )

                        if until_date and pub < until_date:
                            break

                        video_ids.append(
                            item["snippet"]["resourceId"]["videoId"]
                        )

                        collected += 1
                        if collected >= max_videos:
                            break

                    token = data.get("nextPageToken")
                    if not token or collected >= max_videos:
                        break

        return await self.get_video_details(video_ids)

    # =====================================================
    # RELATED
    # =====================================================
    async def get_related_videos(self, video_ids, max_related=50):

        related = []

        async with aiohttp.ClientSession() as session:

            for vid in video_ids:

                token = None
                collected = 0

                while True:

                    params = {
                        "relatedToVideoId": vid,
                        "part": "id",
                        "type": "video",
                        "maxResults": 50,
                        "pageToken": token
                    }

                    data = await self._request(
                        session,
                        "search",
                        params,
                        self.COSTS["search"]
                    )

                    for item in data.get("items", []):
                        related.append(item["id"]["videoId"])
                        collected += 1

                        if collected >= max_related:
                            break

                    token = data.get("nextPageToken")
                    if not token or collected >= max_related:
                        break

        return list(set(related))

    # =====================================================
    # QUOTA
    # =====================================================
    def get_quota_status(self):

        return {
            "used_today": self.used_quota,
            "remaining": self.DAILY_QUOTA_LIMIT - self.used_quota,
            "reset": "Midnight Pacific Time"
        }
        