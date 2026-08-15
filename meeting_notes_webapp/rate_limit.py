import functools
import os
import time
from collections import defaultdict

from flask import jsonify, request

WINDOW_SECONDS = 24 * 60 * 60
CAP = int(os.getenv("DAILY_CAP_PER_IP", "3"))

_hits = defaultdict(list)


def client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr


def rate_limited(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        ip = client_ip()
        now = time.time()
        timestamps = _hits[ip]
        timestamps[:] = [ts for ts in timestamps if now - ts < WINDOW_SECONDS]

        if len(timestamps) >= CAP:
            return jsonify({
                "error": f"Daily limit reached ({CAP} transcriptions). This is a free preview — try again tomorrow."
            }), 429

        timestamps.append(now)
        return f(*args, **kwargs)

    return wrapper
