from slowapi import Limiter
from slowapi.util import get_remote_address

# Tek paylaşımlı limiter instance — tüm router'lara import edilir.
# Default: kullanıcı/IP başına 200/dakika; route-spesifik decorator'larla
# (örn. login 10/dk, register 5/dk) bu sınır ezilir.
# Auth endpoint'leri brute-force'a en açık olduğu için en sıkı limitler orada.
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
