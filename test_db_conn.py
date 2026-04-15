import os
from dotenv import load_dotenv
import asyncio
import asyncpg

# Load .env file
load_dotenv(".env")

DATABASE_URL = os.getenv("DATABASE_URL")

async def test_db():
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Database connection successful!")
        await conn.close()
    except Exception as e:
        print("❌ Database connection failed!")
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_db())