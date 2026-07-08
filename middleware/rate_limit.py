from slowapi import Limiter
from slowapi.util import get_remote_address
from config import settings
import redis

# Try using Redis for rate limit storage if available
redis_online = False
try:
    client = redis.Redis.from_url(settings.REDIS_URL)
    client.ping()
    redis_online = True
except Exception:
    pass

if redis_online:
    limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)
else:
    # Fallback to local in-memory rate limiting
    limiter = Limiter(key_func=get_remote_address)
