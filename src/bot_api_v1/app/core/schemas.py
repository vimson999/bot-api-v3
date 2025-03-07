from pydantic import BaseModel, Field
from datetime import datetime
from typing import Generic, TypeVar, Optional
from enum import IntEnum

class ErrorCode(IntEnum):
    SUCCESS = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_ERROR = 500

T = TypeVar('T')

class BaseResponse(BaseModel, Generic[T]):
    code: int = Field(default=ErrorCode.SUCCESS, example=200, 
                     description="遵循HTTP状态码规范")
    message: str = Field(default="success", example="操作成功",
                       min_length=2, max_length=255)
    data: Optional[T] = Field(default=None, 
                              description="业务数据载荷")
    timestamp: datetime = Field(default_factory=datetime.now,
                               example="2024-05-28T10:30:45.123Z")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        arbitrary_types_allowed = True

class PaginatedData(BaseModel):
    current_page: int = Field(ge=1, example=1)
    page_size: int = Field(ge=1, le=100, example=10)
    total_items: int = Field(ge=0, example=100)
    total_pages: int = Field(ge=0, example=10)
    items: list = Field(default_factory=list)

class PaginatedResponse(BaseResponse[PaginatedData]):
    pass