
from enum import Enum


class MediaType:
    VIDEO = "Video"
    IMAGE = "image"
    UNKNOWN = "unknown"


class MediaPlatform:
    """媒体平台枚举"""
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    BILIBILI = "bilibili"
    WEIBO = "weibo"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    PINTEREST = "pinterest"
    TUMBLR = "tumblr"
    SNAPCHAT = "snapchat"
    VK = "vk"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    KUAISHOU = "kuaishou"
    LINE = "line"
    KAKAO = "kakao"
    WECHAT = "wechat"
    QQ = "qq"
    WEIXIN = "weixin"
    ALIPAY = "alipay"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"
    OTHER = "other"
    UNKNOWN = "unknown"


# 定义常量
class NoteType:
    VIDEO = "视频"
    IMAGE = "图文"
    UNKNOWN = "unknown"
