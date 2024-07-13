from pydantic import BaseModel


class FileUpload(BaseModel):
    file_name: str
    file_type: str
    file_content: str
