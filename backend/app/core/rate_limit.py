from slowapi import Limiter
from slowapi.util import get_remote_address

# Single limiter instance shared across the app.
# Default: 200 req/min per IP (overridden per-route where needed).
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
