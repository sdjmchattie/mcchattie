import asyncio
import os

import asyncpg


# One-off migration: fix Thread.metadata NOT NULL constraint after Chainlit 2.6.5 -> 2.10.0 upgrade.
# NOTE: This approach (idempotent ALTER TABLE at startup) is only suitable for catalogue-only
# changes that complete instantly regardless of table size (e.g. SET DEFAULT, SET/DROP NOT NULL
# via a pre-validated constraint). Any migration that scans or rewrites the table should be run
# manually as a separate step, not at app startup.
async def _migrate():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return
    try:
        conn = await asyncpg.connect(database_url)
        try:
            await conn.execute(
                'ALTER TABLE "Thread" ALTER COLUMN metadata SET DEFAULT \'{}\'::jsonb'
            )
            await conn.execute(
                'UPDATE "Thread" SET metadata = \'{}\' WHERE metadata IS NULL'
            )
        finally:
            await conn.close()
    except Exception as e:
        print(f"Warning: DB migration failed: {e}")


def run_migrations():
    asyncio.run(_migrate())
