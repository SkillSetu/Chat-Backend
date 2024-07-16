from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class FileData(BaseModel):
    name: str
    type: str
    url: str


class ChatMessage(BaseModel):
    id: Optional[str] = None
    sender: Optional[str] = None
    receiver: str
    message: str
    attachments: Optional[list[str]] = None
    file: Optional[FileData] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
