from pydantic import BaseModel, Field
from datetime import datetime
from typing import Generic, TypeVar, Optional, List, Dict, Any
from enum import IntEnum

# 先定义类型变量T，然后才能在BaseResponse中使用
T = TypeVar('T')

# 错误码定义
class ErrorCode(IntEnum):
    SUCCESS = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_ERROR = 500

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

class MediaAuthor(BaseModel):
    id: str = Field(..., description="作者ID")
    sec_id: str = Field(..., description="作者安全ID/唯一标识")
    nickname: str = Field(..., description="作者昵称")
    avatar: Optional[str] = Field(None, description="头像URL")
    signature: Optional[str] = Field(None, description="个人签名")
    verified: Optional[bool] = Field(None, description="是否认证")
    follower_count: Optional[int] = Field(None, description="粉丝数")
    following_count: Optional[int] = Field(None, description="关注数")
    region: Optional[str] = Field(None, description="地区")

class MediaStatistics(BaseModel):
    like_count: Optional[int] = Field(None, description="点赞数")
    comment_count: Optional[int] = Field(None, description="评论数")
    share_count: Optional[int] = Field(None, description="分享数")
    collect_count: Optional[int] = Field(None, description="收藏数")
    play_count: Optional[int] = Field(None, description="播放数")

class MediaInfo(BaseModel):
    cover_url: Optional[str] = Field(None, description="封面URL")
    video_url: Optional[str] = Field(None, description="视频URL")
    duration: Optional[int] = Field(None, description="视频时长(秒)")
    width: Optional[int] = Field(None, description="视频宽度")
    height: Optional[int] = Field(None, description="视频高度")
    quality: Optional[str] = Field(None, description="视频质量")

class RequestContext(BaseModel):
    trace_id: str = Field(..., description="请求跟踪ID")
    app_id: Optional[str] = Field(None, description="应用ID")
    source: Optional[str] = Field(None, description="请求来源")
    user_id: Optional[str] = Field(None, description="用户ID")
    user_name: Optional[str] = Field(None, description="用户名")
    ip: Optional[str] = Field(None, description="客户端IP")
    timestamp: datetime = Field(..., description="请求时间")

class MediaContentResponse(BaseModel):
    platform: str = Field(..., description="平台名称 (douyin, xiaohongshu)")
    video_id: str = Field(..., description="视频ID")
    original_url: str = Field(..., description="原始URL")
    title: Optional[str] = Field(None, description="视频标题")
    description: Optional[str] = Field(None, description="视频描述")
    content: Optional[str] = Field(None, description="视频文案内容")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    author: MediaAuthor = Field(..., description="作者信息")
    statistics: MediaStatistics = Field(..., description="统计信息")
    media: MediaInfo = Field(..., description="媒体信息")
    publish_time: Optional[datetime] = Field(None, description="发布时间")
    update_time: Optional[datetime] = Field(None, description="更新时间")

class MediaExtractResponse(BaseResponse[MediaContentResponse]):
    request_context: Optional[RequestContext] = Field(None, description="请求上下文信息")