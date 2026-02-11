import json
import os
from datetime import datetime, timedelta
import pytz


class QuotaManager:

    DAILY_LIMIT = 10000

    METHOD_COSTS = {
        "search.list": 100,
        "videos.list": 1,
        "channels.list": 1,
        "playlistItems.list": 1
    }

    def __init__(self,
                 quota_file="quota.json",
                 log_file="api_calls.log"):

        self.quota_file = quota_file
        self.log_file = log_file
        self.pt = pytz.timezone("US/Pacific")

        self.quota = self._load_quota()

    # =====================================================
    # DATE HELPERS
    # =====================================================
    def _today_pt(self):
        return datetime.now(self.pt).strftime("%Y-%m-%d")

    def seconds_until_reset(self):

        now = datetime.now(self.pt)

        tomorrow = (
            now.replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )

        return int((tomorrow - now).total_seconds())

    # =====================================================
    # STORAGE
    # =====================================================
    def _load_quota(self):

        if os.path.exists(self.quota_file):
            with open(self.quota_file, "r") as f:
                return json.load(f)

        return {}

    def _save_quota(self):

        with open(self.quota_file, "w") as f:
            json.dump(self.quota, f, indent=2)

    # =====================================================
    # COST RESOLUTION
    # =====================================================
    def resolve_cost(self, method):
        return self.METHOD_COSTS.get(method, 1)

    # =====================================================
    # QUOTA UPDATE
    # =====================================================
    def add_usage(self, api_key, method):

        cost = self.resolve_cost(method)
        date = self._today_pt()

        # дата → ключ → квота
        self.quota.setdefault(date, {})
        self.quota[date].setdefault(api_key, 0)

        self.quota[date][api_key] += cost

        self._save_quota()

    def get_usage(self, api_key):

        date = self._today_pt()

        return self.quota.get(date, {}).get(api_key, 0)

    # =====================================================
    # LOGGING
    # =====================================================
    def log_call(self, api_key, method, params, caller, purpose):

        cost = self.resolve_cost(method)
        
        dt = datetime.utcnow()
        dtstr = dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"

        record = {
            "time_utc": dtstr,
            #"api_key": api_key,
            "cost": cost,
            #"caller": caller,
            #"purpose": purpose,
            "method": method,
            "params": params,
        }
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # =====================================================
    # STATUS
    # =====================================================
    def get_status(self, api_key):

        used = self.get_usage(api_key)

        return {
            "used": used,
            "remaining": self.DAILY_LIMIT - used,
            "seconds_until_reset": self.seconds_until_reset()
        }
        