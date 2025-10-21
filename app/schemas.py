from pydantic import BaseModel
from datetime import datetime
from typing import Dict

class StringCreate(BaseModel):
    value: str

class StringResponse(BaseModel):
    id: str
    value: str
    length: int
    is_palindrome: bool
    unique_characters: int
    word_count: int
    character_frequency_map: Dict[str, int]
    created_at: datetime

    class Config:
        orm_mode = True
