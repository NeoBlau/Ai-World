"""Create the test database if it does not exist (used by `make test`)."""

import asyncio
import os
from urllib.parse import urlparse

import asyncpg


async def main() -> None:
    url = urlparse(os.environ["TEST_DATABASE_URL"].replace("+asyncpg", ""))
    name = url.path.lstrip("/")
    conn = await asyncpg.connect(f"postgresql://{url.username}:{url.password}@{url.hostname}:{url.port or 5432}/postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
