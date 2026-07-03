import redis
from datetime import datetime
from config import settings

class LocalMemoryRedisMock:
    def __init__(self):
        self.store = {}
        self.expiries = {}

    def ping(self):
        return True

    def get(self, key: str):
        if key in self.expiries:
            if datetime.utcnow().timestamp() > self.expiries[key]:
                del self.store[key]
                del self.expiries[key]
                return None
        return self.store.get(key)

    def set(self, key: str, value: str, ex=None):
        self.store[key] = value
        if ex:
            self.expiries[key] = datetime.utcnow().timestamp() + ex
        return True

    def delete(self, key: str):
        count = 0
        if key in self.store:
            del self.store[key]
            count += 1
        if key in self.expiries:
            del self.expiries[key]
        return count

    def keys(self, pattern: str):
        import fnmatch
        return [k for k in self.store.keys() if fnmatch.fnmatch(k, pattern)]

class RedisClientWrapper:
    def __init__(self):
        self.client = None
        self.fallback = None
        self.try_connect()

    def ping(self):
        if self.client:
            try:
                return self.client.ping()
            except Exception:
                self.client = None
                self.fallback = LocalMemoryRedisMock()
        return self.fallback.ping()

    def try_connect(self):
        try:
            self.client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            self.client.ping()
            print("Connected to Redis for token registry")
        except Exception as e:
            print(f"Warning: Failed to connect to Redis ({e}). Using in-memory security store.")
            self.client = None
            self.fallback = LocalMemoryRedisMock()

    def get(self, key: str):
        if self.client:
            try:
                return self.client.get(key)
            except Exception:
                self.client = None
                self.fallback = LocalMemoryRedisMock()
        return self.fallback.get(key)

    def set(self, key: str, value: str, ex=None):
        if self.client:
            try:
                return self.client.set(key, value, ex=ex)
            except Exception:
                self.client = None
                self.fallback = LocalMemoryRedisMock()
        return self.fallback.set(key, value, ex=ex)

    def delete(self, key: str):
        if self.client:
            try:
                return self.client.delete(key)
            except Exception:
                self.client = None
                self.fallback = LocalMemoryRedisMock()
        return self.fallback.delete(key)

    def keys(self, pattern: str):
        if self.client:
            try:
                return self.client.keys(pattern)
            except Exception:
                self.client = None
                self.fallback = LocalMemoryRedisMock()
        return self.fallback.keys(pattern)

redis_wrapper = RedisClientWrapper()
