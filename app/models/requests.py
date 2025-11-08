"""
Pydantic request/response models
"""
from pydantic import BaseModel
from typing import Optional


class AnalyzeRequest(BaseModel):
    file_id: str


class ChatRequest(BaseModel):
    message: str
    file_id: Optional[str] = None


class AnalysisStatus(BaseModel):
    status: str  # "pending", "processing", "completed", "failed"
    progress: int  # 0-100
    message: str

