from dotenv import load_dotenv

from motor.motor_asyncio import AsyncIOMotorClient

from ..config import config


load_dotenv(override=True)

client = AsyncIOMotorClient(config.MONGO_URI)
db = client["skillarena-dev"]
