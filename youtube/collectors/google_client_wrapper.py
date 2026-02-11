import threading
import time
from collections import deque
from googleapiclient.discovery import build
import httplib2


class GoogleClientWrapper:
    """
    api_configs format:

    [
        {
            "api_key": "KEY1",
            "proxy": "http://user:pass@ip:port"   # optional
        },
        {
            "api_key": "KEY2"                     # без проксі
        }
    ]
    """

    def __init__(self,
                 api_configs,
                 quota_manager,
                 caller_tag,
                 purpose_tag,
                 requests_per_second=5):

        self.qm = quota_manager
        self.caller = caller_tag
        self.purpose = purpose_tag
        self.rps = requests_per_second

        self.keys = []
        self.clients = {}
        self.rate_windows = {}
        self.locks = {}

        self.current_key_index = 0
        self.rotation_lock = threading.Lock()

        # ---------- INIT CLIENTS ----------
        for conf in api_configs:

            key = conf["api_key"]
            proxy = conf.get("proxy")

            if proxy:
                proxy_info = httplib2.ProxyInfo.from_url(proxy)
                http = httplib2.Http(proxy_info=proxy_info)

                client = build(
                    "youtube",
                    "v3",
                    developerKey=key,
                    http=http
                )
            else:
                client = build("youtube", "v3", developerKey=key)

            self.keys.append(key)
            self.clients[key] = client
            self.rate_windows[key] = deque()
            self.locks[key] = threading.Lock()

    # =====================================================
    # RESET DETECTOR
    # =====================================================
    def _reset_if_needed(self):

        # якщо у першого ключа квота обнулилась
        key = self.keys[0]

        if self.qm.get_usage(key) == 0:
            self.current_key_index = 0

    # =====================================================
    # KEY ROTATION
    # =====================================================
    def _choose_key(self, method_name):

        cost = self.qm.resolve_cost(method_name)

        with self.rotation_lock:

            self._reset_if_needed()

            for _ in range(len(self.keys)):

                key = self.keys[self.current_key_index]

                remaining = (
                    self.qm.DAILY_LIMIT -
                    self.qm.get_usage(key)
                )

                if remaining >= cost:
                    return key

                # rotate
                self.current_key_index = (
                    self.current_key_index + 1
                ) % len(self.keys)

        raise RuntimeError("All API keys exhausted")

    # =====================================================
    # SLIDING WINDOW THROTTLE
    # =====================================================
    def _throttle(self, key):

        window = self.rate_windows[key]

        with self.locks[key]:

            now = time.time()

            # очищаємо старі timestamps
            while window and (now - window[0]) > 1:
                window.popleft()

            if len(window) >= self.rps:

                sleep_time = 1 - (now - window[0])
                if sleep_time > 0:
                    threading.Event().wait(sleep_time)

            window.append(time.time())

    # =====================================================
    # EXECUTE
    # =====================================================
    def execute(self, method_callable, method_name, params):

        last_error = None

        for _ in range(len(self.keys)):

            key = self._choose_key(method_name)
            client = self.clients[key]

            try:

                self._throttle(key)

                request = method_callable(client, **params)
                response = request.execute()

                self.qm.add_usage(key, method_name)

                self.qm.log_call(
                    key,
                    method_name,
                    params,
                    self.caller,
                    self.purpose
                )

                return response

            except Exception as e:

                last_error = e

                # rotate key
                with self.rotation_lock:
                    self.current_key_index = (
                        self.current_key_index + 1
                    ) % len(self.keys)

        raise last_error
        