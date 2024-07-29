from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId
from typing import Optional


class FileData(BaseModel):
    name: str
    type: str
    url: str


class Message(BaseModel):
    sender: Optional[str] = None
    receiver: str
    message: str
    file: Optional[FileData] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    messages: list[Message]
    users: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
