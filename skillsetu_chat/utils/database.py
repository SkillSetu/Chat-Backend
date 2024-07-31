import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv(override=True)

print(os.getenv("MONGO_URI"))
client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = client["skillarena-dev"]
