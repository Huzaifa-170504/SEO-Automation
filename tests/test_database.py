
import asyncio

from sqlalchemy import inspect

from app.storage.database import init_db, close_db, engine


async def main():
    try:
        await init_db()

        async with engine.connect() as connection:
            table_names = await connection.run_sync(
                lambda sync_connection: inspect(
                    sync_connection
                ).get_table_names()
            )

        print("Database initialized successfully.")
        print("Tables created:")

        for table_name in table_names:
            print(f"- {table_name}")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())