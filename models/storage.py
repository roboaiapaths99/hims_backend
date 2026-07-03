from pydantic import BaseModel
from datetime import datetime

class FileUploadResponse(BaseModel):
    id: str
    filename: str
    original_name: str
    mime_type: str
    size: int
    url: str

    class Config:
        from_attributes = True

class FileDownloadResponse(BaseModel):
    download_url: str
    expires_at: datetime
