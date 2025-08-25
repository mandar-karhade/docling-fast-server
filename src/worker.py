import os
from redis import Redis
from rq import Worker, Queue, Connection

listen = ['default']

redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')

if not redis_url or not redis_token:
    raise ValueError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required")

# The redis-py client doesn't directly support the `token` parameter.
# We need to construct the DSN with the token.
# For Upstash, the URL should be in the format: rediss://:<token>@<host>:<port>
# The URL from Upstash is in the format https://<host>
# We need to convert it to rediss://:<token>@<host>:42548 (assuming port is always the same)
rest_url_parts = redis_url.replace("https://", "").split(".")
redis_host = f"{rest_url_parts[0]}.upstash.io"
redis_dsn = f"rediss://:{redis_token}@{redis_host}:42548"


conn = Redis.from_url(redis_dsn)


if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
