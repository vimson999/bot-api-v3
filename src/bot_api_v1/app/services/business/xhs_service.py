import os
import sys
from pathlib import Path
import asyncio
import json
import time
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

from bot_api_v1.app.core.cache import cache_result
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.services.business.script_service import ScriptService, AudioDownloadError, AudioTranscriptionError

# 定义常量
class NoteType:
    VIDEO = "视频"
    IMAGE = "图文"
    UNKNOWN = "unknown"

class MediaType:
    VIDEO = "video"
    IMAGE = "image"
    UNKNOWN = "unknown"

# # 通过环境变量或相对路径获取项目根目录
# ROOT_DIR = Path(os.getenv("BOT_API_ROOT", str(Path(__file__).resolve().parents[4])))
# SPIDER_XHS_PATH = ROOT_DIR / "libs" / "spider_xhs"
# # 设置NODE_PATH指向子模块的node_modules目录
# os.environ["NODE_PATH"] = str(SPIDER_XHS_PATH / "node_modules")
# # 添加子模块路径到系统路径
# sys.path.append(str(SPIDER_XHS_PATH))


# 确定项目根目录和Spider_XHS路径
ROOT_DIR = Path(__file__).parent.parent.parent.parent
SPIDER_XHS_PATH = ROOT_DIR / "libs" / "spider_xhs"
# 设置NODE_PATH指向子模块的node_modules目录
os.environ["NODE_PATH"] = str(SPIDER_XHS_PATH / "node_modules")
sys.path.append(str(SPIDER_XHS_PATH))


# 导入小红书子模块
try:
    # from apis.pc_apis import XHS_Apis
    # from xhs_utils.data_util import handle_note_info, download_note
    # from xhs_utils.common_utils import init as xhs_init, load_env
    
    from bot_api_v1.libs.spider_xhs.apis.pc_apis import XHS_Apis
    from bot_api_v1.libs.spider_xhs.xhs_utils.data_util import handle_note_info, download_note
    from bot_api_v1.libs.spider_xhs.xhs_utils.common_utils import init as xhs_init, load_env


    SPIDER_XHS_LOADED = True
except ImportError as e:
    logger.error(f"无法导入小红书子模块: {str(e)}")
    SPIDER_XHS_LOADED = False

    # 创建stub类，以便在模块加载失败时服务仍能启动
    class XHS_Apis:
        """当Spider_XHS模块无法加载时的替代类"""
        def __init__(self):
            self.error_message = "小红书模块未正确加载，无法提供服务"
            logger.error(self.error_message)
            
        def get_note_info(self, *args, **kwargs):
            logger.error(f"{self.error_message} - get_note_info被调用")
            return False, self.error_message, None

        def get_user_info(self, *args, **kwargs):
            logger.error(f"{self.error_message} - get_user_info被调用")
            return False, self.error_message, None
            
        def search_some_note(self, *args, **kwargs):
            logger.error(f"{self.error_message} - search_some_note被调用")
            return False, self.error_message, None
            
        def get_note_all_comment(self, *args, **kwargs):
            logger.error(f"{self.error_message} - get_note_all_comment被调用")
            return False, self.error_message, None
            
        def get_search_keyword(self, *args, **kwargs):
            logger.error(f"{self.error_message} - get_search_keyword被调用")
            return False, self.error_message, None
            
        def get_user_all_notes(self, *args, **kwargs):
            logger.error(f"{self.error_message} - get_user_all_notes被调用")
            return False, self.error_message, None
    
    # 创建模拟xhs_init函数
    def xhs_init():
        logger.error("小红书初始化失败 - 模块未加载")
        return None, {"media": str(ROOT_DIR / "downloads")}
    
    # 创建模拟load_env函数  
    def load_env():
        logger.error("小红书加载环境变量失败 - 模块未加载")
        return ""


class XHSError(Exception):
    """小红书服务操作过程中出现的错误"""
    pass


class XHSService:
    """小红书服务，提供小红书相关的业务操作"""
    
    def __init__(self, 
                 api_timeout: int = 30,
                 cache_duration: int = 3600,
                 cookies_file: Optional[str] = None):
        """
        初始化小红书服务
        
        Args:
            api_timeout: API请求超时时间(秒)
            cache_duration: 缓存持续时间(秒)
            cookies_file: Cookie文件路径，默认使用配置目录中的文件
        """
        self.api_timeout = api_timeout
        self.cache_duration = cache_duration
        
        # 初始化 ScriptService 用于音频处理
        self.script_service = ScriptService()
        
        # 初始化小红书API
        self.xhs_apis = XHS_Apis()
        
        # 加载Cookies
        default_cookies_path = ROOT_DIR / "app" / "config" / "cookies" / "cookies_xhs.txt"
        self.cookies_path = cookies_file if cookies_file and os.path.exists(cookies_file) else default_cookies_path
        self.cookies_str = self._load_cookies()
        
        # 初始化基础路径
        try:
            _, self.base_path = xhs_init()
            if not self.base_path or not isinstance(self.base_path, dict):
                # 确保base_path有效
                self.base_path = {"media": str(ROOT_DIR / "downloads")}

            logger.info(f"小红书初始化成功，NODE_PATH is : {os.environ["NODE_PATH"]}")
        except Exception as e:
            logger.warning(f"小红书初始化失败: {str(e)}")
            self.base_path = {"media": str(ROOT_DIR / "downloads")}

        # 创建下载目录
        os.makedirs(self.base_path.get("media", str(ROOT_DIR / "downloads")), exist_ok=True)
    
    def _load_cookies(self) -> str:
        """从文件或环境变量加载Cookie"""
        try:
            if os.path.exists(self.cookies_path):
                with open(self.cookies_path, 'r', encoding='utf-8') as f:
                    cookies = f.read().strip()
                    logger.info(f"从文件加载小红书Cookies成功: {self.cookies_path}")
                    return cookies
            else:
                # 从环境变量加载Cookie
                cookies = load_env()
                if cookies:
                    logger.info("从环境变量加载小红书Cookies成功")
                    return cookies
                else:
                    logger.warning("无法加载小红书Cookies，将影响API功能")
                    return ""
        except Exception as e:
            logger.error(f"加载小红书Cookies失败: {str(e)}")
            return ""
    
    @gate_keeper()
    @log_service_call(method_type="xhs", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def get_note_info(self, note_url: str, extract_text: bool = False, cal_points: bool = True) -> Dict[str, Any]:
        """
        获取小红书笔记信息
        
        Args:
            note_url: 小红书笔记URL
            extract_text: 是否提取文案，默认为False
                
        Returns:
            Dict[str, Any]: 笔记信息，包含标题、作者、描述等
                
        Raises:
            XHSError: 处理过程中出现的错误
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        
        logger.info(f"开始获取小红书笔记信息: {note_url}, extract_text={extract_text}", 
                extra={"request_id": trace_key})
        
        if not SPIDER_XHS_LOADED:
            error_msg = "小红书模块未正确加载，无法获取笔记信息"
            logger.error(error_msg, extra={"request_id": trace_key})
            raise XHSError(error_msg)
        
        try:
            if cal_points :
                total_required = 10  # 基础消耗10分
                
                # 从上下文获取积分信息
                points_info = request_ctx.get_points_info()
                available_points = points_info.get('available_points', 0)
                
                # 验证积分是否足够
                if available_points < total_required:
                    error_msg = f"获取基本信息时积分不足: 需要 {total_required} 积分您当前仅有 {available_points} 积分"
                    logger.info_to_db(error_msg, extra={"request_id": trace_key})
                    raise AudioTranscriptionError(error_msg)
                
                logger.info_to_db(f"获取基本信息时检查通过：所需 {total_required} 积分，可用 {available_points} 积分，需要记录这个消耗", 
                        extra={"request_id": trace_key})

            # 使用asyncio.wait_for添加超时控制
            async def get_note_with_timeout():
                # 由于XHS_Apis不是异步的，使用run_in_executor在线程池中执行
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, 
                    lambda: self.xhs_apis.get_note_info(note_url, self.cookies_str)
                )
            
            try:
                success, msg, note_data = await asyncio.wait_for(
                    get_note_with_timeout(), 
                    timeout=self.api_timeout
                )
            except asyncio.TimeoutError:
                raise XHSError(f"获取小红书笔记信息超时(>{self.api_timeout}秒)")
            
            if not success or not note_data:
                error_msg = f"获取小红书笔记信息失败: {msg}"
                logger.error(error_msg, extra={"request_id": trace_key})
                raise XHSError(error_msg)
            
            # 解析返回的数据结构
            try:
                note_info = note_data['data']['items'][0]
                note_info['url'] = note_url
                note_info = handle_note_info(note_info)
            except (KeyError, IndexError) as e:
                logger.error(f"解析小红书笔记数据失败: {str(e)}", extra={"request_id": trace_key})
                raise XHSError(f"解析笔记数据失败: {str(e)}")
            
            # 转换为统一的格式
            result = self._convert_note_to_standard_format(note_info)
            
            if cal_points:
                request_ctx.set_consumed_points(total_required, "获取基本信息")

            # 提取视频文案（如果需要）
            if extract_text and result.get("type") == MediaType.VIDEO and result.get("media", {}).get("video_url"):
                try:
                    video_url = result.get("media", {}).get("video_url", "")
                    if not video_url:
                        logger.warning(f"无法获取小红书视频URL，跳过文案提取", extra={"request_id": trace_key})
                        result["transcribed_text"] = "无法获取视频URL"
                    else:
                        logger.info(f"开始提取小红书视频文案: {result.get('note_id', '')}", extra={"request_id": trace_key})
                        
                        # 下载视频
                        try:
                            audio_path, audio_title = await self.script_service.download_audio(video_url)
                            
                            # 转写音频
                            transcribed_text = await self.script_service.transcribe_audio(audio_path)
                            
                            # 添加到结果中
                            result["transcribed_text"] = transcribed_text
                            logger.info(f"成功提取小红书视频文案", extra={"request_id": trace_key})
                        except AudioDownloadError as e:
                            logger.error(f"下载小红书视频失败: {str(e)}", extra={"request_id": trace_key})
                            result["transcribed_text"] = f"下载视频失败: {str(e)}"
                        except AudioTranscriptionError as e:
                            logger.error(f"转写小红书视频失败: {str(e)}", extra={"request_id": trace_key})
                            result["transcribed_text"] = f"转写视频失败: {str(e)}"
                except Exception as e:
                    logger.error(f"提取小红书视频文案失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                    result["transcribed_text"] = f"提取文案失败: {str(e)}"
            
            logger.info(f"成功获取小红书笔记信息: {result.get('note_id', '')}", extra={"request_id": trace_key})
            return result
                
        except XHSError:
            # 重新抛出XHSError
            raise
        except Exception as e:
            error_msg = f"获取小红书笔记信息失败: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            raise XHSError(error_msg) from e
    
    def _convert_note_to_standard_format(self, note_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        将原始小红书笔记数据转换为标准格式
        
        Args:
            note_info: 原始小红书笔记数据
            
        Returns:
            Dict[str, Any]: 标准格式的笔记数据
        """
        try:
            # 判断笔记类型
            note_type = note_info.get('note_type', '')
            is_video = note_type == NoteType.VIDEO
            
            # 构造媒体信息
            media_info = {
                "cover_url": note_info.get('video_cover', note_info.get('image_list', [''])[0]),
                "type": MediaType.VIDEO if is_video else MediaType.IMAGE
            }
            
            # 处理视频特有信息
            if is_video:
                media_info.update({
                    "video_url": note_info.get('video_addr', ''),
                    "duration": 0,  # 小红书API没有提供视频时长
                    "width": 0,     # 小红书API没有提供视频宽度
                    "height": 0     # 小红书API没有提供视频高度
                })
            
            # 构造统计数据
            statistics = {
                "like_count": self._parse_count_string(note_info.get('liked_count', '0')),
                "comment_count": self._parse_count_string(note_info.get('comment_count', '0')),
                "share_count": self._parse_count_string(note_info.get('share_count', '0')),
                "collected_count": self._parse_count_string(note_info.get('collected_count', '0')),
                "view_count": 0  # 小红书API没有提供观看数
            }
            
            # 构造作者信息 - 基础信息
            author = {
                "id": note_info.get('user_id', ''),
                "nickname": note_info.get('nickname', ''),
                "avatar": note_info.get('avatar', ''),
                "signature": "",  # 笔记API中没有个人签名
                "verified": False,  # 笔记API中没有认证信息
                "follower_count": 0,  # 笔记API中没有粉丝数
                "following_count": 0,  # 笔记API中没有关注数
                "notes_count": 0,  # 笔记API中没有笔记数
                "location": note_info.get('ip_location', '')
            }
            
            # 构造标准格式的结果
            result = {
                "note_id": note_info.get('note_id', ''),
                "title": note_info.get('title', ''),
                "desc": note_info.get('desc', ''),
                "type": MediaType.VIDEO if is_video else MediaType.IMAGE,
                "author": author,
                "statistics": statistics,
                "tags": note_info.get('tags', []),
                "media": media_info,
                "images": note_info.get('image_list', []),
                "original_url": note_info.get('note_url', note_info.get('url', '')),
                "create_time": note_info.get('upload_time', ''),
                "last_update_time": note_info.get('upload_time', '')  # 小红书API没有更新时间，使用上传时间
            }
            
            # 转换时间字符串为时间戳（如果有）
            if result["create_time"] and isinstance(result["create_time"], str):
                result["create_time"] = self._parse_datetime_string(result["create_time"])
            
            if result["last_update_time"] and isinstance(result["last_update_time"], str):
                result["last_update_time"] = self._parse_datetime_string(result["last_update_time"])
            
            return result
        except Exception as e:
            logger.error(f"转换小红书笔记格式失败: {str(e)}")
            # 返回基本信息，避免整个流程失败
            return {
                "note_id": note_info.get('note_id', ''),
                "title": note_info.get('title', ''),
                "desc": note_info.get('desc', ''),
                "type": MediaType.UNKNOWN,
                "author": {"id": note_info.get('user_id', ''), "nickname": note_info.get('nickname', '')},
                "statistics": {},
                "tags": [],
                "media": {},
                "original_url": note_info.get('note_url', '')
            }
    
    def _parse_count_string(self, count_str: str) -> int:
        """将字符串形式的数量转换为整数"""
        try:
            if not count_str or count_str == "0":
                return 0
                
            # 处理带单位的字符串，如"1.2万"
            if '万' in count_str:
                num = float(count_str.replace('万', ''))
                return int(num * 10000)
            elif '亿' in count_str:
                num = float(count_str.replace('亿', ''))
                return int(num * 100000000)
            else:
                # 尝试直接转换为整数
                return int(count_str)
        except (ValueError, TypeError):
            # 更明确的错误处理
            logger.debug(f"无法解析数量字符串: {count_str}")
            return 0
    
    def _parse_datetime_string(self, date_str: str) -> int:
        """
        解析多种可能的日期时间字符串为时间戳
        
        Args:
            date_str: 日期时间字符串
            
        Returns:
            int: Unix时间戳
        """
        if not date_str:
            return 0
            
        try:
            # 尝试多种可能的时间格式
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y/%m/%d"
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return int(dt.timestamp())
                except ValueError:
                    continue
            
            # 所有格式都尝试失败
            logger.warning(f"无法解析日期时间字符串: {date_str}")
            return 0
        except Exception as e:
            logger.error(f"解析日期时间出错: {str(e)}")
            return 0
    
    @gate_keeper()
    @log_service_call(method_type="xhs", tollgate="10-3")
    @cache_result(expire_seconds=600)
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        获取小红书用户信息
        
        Args:
            user_id: 小红书用户ID或URL
            
        Returns:
            Dict[str, Any]: 用户信息，包含昵称、关注数、粉丝数等
            
        Raises:
            XHSError: 处理过程中出现的错误
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        
        logger.info(f"开始获取小红书用户信息: {user_id}", extra={"request_id": trace_key})
        
        if not SPIDER_XHS_LOADED:
            error_msg = "小红书模块未正确加载，无法获取用户信息"
            logger.error(error_msg, extra={"request_id": trace_key})
            raise XHSError(error_msg)
        
        try:
            # 处理可能传入的URL
            if user_id.startswith("http"):
                try:
                    # 用 urllib.parse 从URL中提取user_id
                    import urllib.parse
                    parsed_url = urllib.parse.urlparse(user_id)
                    path_parts = [p for p in parsed_url.path.split("/") if p]
                    # 获取最后一部分作为user_id
                    if path_parts:
                        extracted_id = path_parts[-1]
                        if extracted_id:
                            user_id = extracted_id
                            logger.info(f"从URL中提取用户ID: {user_id}", extra={"request_id": trace_key})
                except Exception as e:
                    logger.warning(f"从URL提取用户ID失败: {str(e)}", extra={"request_id": trace_key})
            
            # 使用asyncio.wait_for添加超时控制
            async def get_user_with_timeout():
                # 由于XHS_Apis不是异步的，使用run_in_executor在线程池中执行
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, 
                    lambda: self.xhs_apis.get_user_info(user_id, self.cookies_str)
                )
            
            try:
                success, msg, user_data = await asyncio.wait_for(
                    get_user_with_timeout(), 
                    timeout=self.api_timeout
                )
            except asyncio.TimeoutError:
                raise XHSError(f"获取小红书用户信息超时(>{self.api_timeout}秒)")
            
            if not success or not user_data:
                error_msg = f"获取小红书用户信息失败: {msg}"
                logger.error(error_msg, extra={"request_id": trace_key})
                raise XHSError(error_msg)
            
            # 转换为标准格式
            result = self._convert_user_to_standard_format(user_data)
            
            logger.info(f"成功获取小红书用户信息: {result.get('user_id', '')}", extra={"request_id": trace_key})
            return result
                
        except XHSError:
            # 重新抛出XHSError
            raise
        except Exception as e:
            error_msg = f"获取小红书用户信息失败: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            raise XHSError(error_msg) from e
    
    def _convert_user_to_standard_format(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将原始小红书用户数据转换为标准格式
        
        Args:
            user_data: 原始小红书用户数据
            
        Returns:
            Dict[str, Any]: 标准格式的用户数据
        """
        try:
            # 提取基本信息
            basic_info = user_data.get('basic_info', {})
            if not basic_info and 'data' in user_data:
                # 可能是不同的API返回格式
                basic_info = user_data.get('data', {}).get('user', {})
            
            # 提取交互数据
            interactions = user_data.get('interactions', [])
            follower_count = 0
            following_count = 0
            notes_count = 0
            interaction_count = 0
            
            for item in interactions:
                item_type = item.get('type', '')
                count_str = item.get('count', '0')
                
                if item_type == 'fans':
                    follower_count = self._parse_count_string(count_str)
                elif item_type == 'follows':
                    following_count = self._parse_count_string(count_str)
                elif item_type == 'notes':
                    notes_count = self._parse_count_string(count_str)
                elif item_type == 'interaction':
                    interaction_count = self._parse_count_string(count_str)
            
            # 提取标签信息
            tags = user_data.get('tags', [])
            tag_names = [tag.get('name', '') for tag in tags if 'name' in tag]
            
            # 判断是否认证
            verified = False
            verified_reason = ""
            for tag in tags:
                if tag.get('tagType') == 'profession':
                    verified = True
                    verified_reason = tag.get('name', '')
                    break
            
            # 构造标准格式结果
            result = {
                "user_id": basic_info.get('red_id', ''),
                "nickname": basic_info.get('nickname', ''),
                "avatar": basic_info.get('images', ''),
                "description": basic_info.get('desc', ''),
                "gender": basic_info.get('gender', 0),
                "location": basic_info.get('ip_location', ''),
                "verified": verified,
                "verified_reason": verified_reason,
                "statistics": {
                    "following_count": following_count,
                    "follower_count": follower_count,
                    "notes_count": notes_count,
                    "interaction_count": interaction_count
                },
                "tags": tag_names
            }
            
            return result
        except Exception as e:
            logger.error(f"转换小红书用户格式失败: {str(e)}")
            # 返回基本信息，避免整个流程失败
            return {
                "user_id": "",
                "nickname": user_data.get('basic_info', {}).get('nickname', '') if 'basic_info' in user_data else "",
                "avatar": "",
                "description": "",
                "statistics": {
                    "following_count": 0,
                    "follower_count": 0,
                    "notes_count": 0
                }
            }

    # --- 新增的同步方法 (供 Celery 调用) ---
    def get_note_info_sync_for_celery(
        self, 
        url: str, 
        extract_text: bool, 
        # --- 替代 request_ctx 的参数 ---
        user_id_for_points: str, # 假设用于积分或日志
        trace_id: str,
        root_trace_key: str
    ) -> dict:
        """
        [同步执行] 获取小红书笔记信息，并可选提取文本。
        为 Celery Task 设计，不依赖 request_ctx，不写数据库。
        """
        log_extra = {"request_id": trace_id, "user_id": user_id_for_points,"root_trace_key": root_trace_key}
        logger.info(f"[Sync XHS] 开始获取笔记信息: {url}, extract_text={extract_text}", extra=log_extra)
        
        if not SPIDER_XHS_LOADED:
             raise XHSError("小红书模块未加载")

        points_consumed = 0 # 初始化消耗积分
        base_cost = 10      # 基础信息成本
        transcription_cost = 0 # 初始化转写成本
        media_data = None
        transcribed_text = None
        
        try:
            # 1. 获取基础笔记信息 (调用同步/阻塞的 XHS API)
            # 假设 self.xhs_apis.get_note_info 是阻塞的
            logger.debug("[Sync XHS] 调用 xhs_apis.get_note_info...", extra=log_extra)
            success, msg, note_data_raw = self.xhs_apis.get_note_info(url, self.cookies_str)
            logger.debug(f"[Sync XHS] xhs_apis.get_note_info 返回: success={success}", extra=log_extra)
            
            if not success or not note_data_raw:
                raise XHSError(f"获取小红书笔记API失败: {msg}")
            
            # 解析数据 (这部分是同步的)
            try:
                note_data_raw['data']['items'][0]['url'] = url # 添加原始 URL
                note_info_parsed = handle_note_info(note_data_raw['data']['items'][0])
                media_data = self._convert_note_to_standard_format(note_info_parsed)
                points_consumed += base_cost # 累加基础积分
            except (KeyError, IndexError, Exception) as e:
                 logger.error(f"[Sync XHS] 解析笔记数据失败: {e}", exc_info=True, extra=log_extra)
                 raise XHSError(f"解析笔记数据失败: {str(e)}")

            # 2. 如果需要提取文本
            if extract_text and media_data.get("type") == MediaType.VIDEO:
                video_url = media_data.get("media", {}).get("video_url")
                if video_url:
                    logger.info(f"[Sync XHS] 开始下载和转写视频...", extra=log_extra)
                    try:
                        # 调用 ScriptService 新增的同步方法
                        audio_path, _ = self.script_service.download_audio_sync(video_url, trace_id)
                        transcribed_text,audio_duration_sec = self.script_service.transcribe_audio_sync(audio_path, trace_id)
                        
                        # 假设转写成功，计算积分 (需要实际逻辑)
                        # audio_duration_sec = 120 # !! 需要从 download_audio_sync 获取或重新计算 !!
                        duration_points = ((audio_duration_sec // 60) + (1 if audio_duration_sec % 60 > 0 else 0)) * 10
                        transcription_cost = max(10, duration_points) # 保证最低 10 分
                        points_consumed = transcription_cost

                        logger.info(f"[Sync XHS] 视频转写成功", extra=log_extra)
                    except (AudioDownloadError, AudioTranscriptionError) as e:
                        logger.error(f"[Sync XHS] 下载或转写失败: {e}", extra=log_extra)
                        transcribed_text = f"提取文本失败: {str(e)}"
                        transcription_cost = 0 # 失败不计积分
                    except Exception as e:
                         logger.error(f"[Sync XHS] 提取文本发生意外错误: {e}", exc_info=True, extra=log_extra)
                         transcribed_text = f"提取文本时发生内部错误 ({trace_id})"
                         transcription_cost = 0
                else:
                    transcribed_text = "无法获取视频URL进行转写"
                    logger.warning("[Sync XHS] 未找到视频URL", extra=log_extra)
                
                # 将转写结果（或错误信息）添加到结果中
                media_data["content"] = transcribed_text 
            
            # 累加总积分
            # points_consumed += transcription_cost
            
            logger.info(f"[Sync XHS] 处理成功完成: {url}", extra=log_extra)
            return {"status": "success", "data": media_data, "points_consumed": points_consumed}

        except (XHSError, MediaError) as e: # 捕获已知的业务错误
             error_msg = f"处理失败 ({type(e).__name__}): {str(e)}"
             logger.error(f"[Sync XHS] {error_msg}", extra=log_extra)
             return {"status": "failed", "error": error_msg, "points_consumed": 0}
        except Exception as e: # 捕获其他意外错误
             error_msg = f"发生意外错误: {str(e)}"
             logger.error(f"[Sync XHS] {error_msg}", exc_info=True, extra=log_extra)
             return {"status": "failed", "error": f"发生内部错误 ({trace_id})", "exception": str(e), "points_consumed": 0}


    def get_search_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索小红书笔记信息

        Args:
            keyword: 搜索关键词
            count: 搜索结果数量，默认为10

        Returns:
            List[Dict[str, Any]]: 搜索结果列表，每个结果包含笔记信息
        """
        logger.info(f"开始搜索小红书笔记: {keyword}")
        success, msg, res_json = self.xhs_apis.get_search_keyword(keyword, self.cookies_str)

        return success, msg, res_json

    
    def get_search_some_note(
        self, 
        trace_id: str,
        platform: str, 
        query: str, 
        num: int, 
        sort: str ) -> List[Dict[str, Any]]:
        """
        搜索小红书笔记信息
        """
        logger.info(f"[XHS][search_some_note] 开始搜索小红书笔记: query={query}, num={num}, sort={sort}, platform={platform}", extra={"trace_id": trace_id})
        try:
            query_num = num
            note_type = 0
            success, msg, notes = self.xhs_apis.search_some_note(query, query_num, self.cookies_str, sort, note_type)
            if not success:
                logger.error(f"[XHS][search_some_note] 搜索失败: {msg}", extra={"trace_id": trace_id, "platform": platform, "query": query, "num": num, "sort": sort})
                return []
            logger.info(f"[XHS][search_some_note] 搜索成功: success={success}, msg={msg}, count={len(notes)}", extra={"trace_id": trace_id, "platform": platform, "query": query, "num": num, "sort": sort})
            return notes
        except Exception as e:
            logger.error(f"[XHS][search_some_note] 搜索异常: {str(e)}", exc_info=True, extra={"trace_id": trace_id, "platform": platform, "query": query, "num": num, "sort": sort})
            return []

    async def async_get_search_some_note(self, trace_key:str, platform: str, query: str, num: int, sort: str) -> List[Dict[str, Any]]:
        """
        异步搜索小红书笔记信息
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_search_some_note, trace_key,platform,query,num,sort)



    async def async_get_note_all_comment(self, note_url: str,log_extra:Dict[str, Any]) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_note_all_comment, note_url ,log_extra)
    

    # @async_cache_result(expire_seconds=600,prefix="xhs_service")
    def get_note_all_comment(self, note_url: str,log_extra:Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        搜索小红书笔记信息

        Args:
            keyword: 搜索关键词
            count: 搜索结果数量，默认为10

        Returns:
            List[Dict[str, Any]]: 搜索结果列表，每个结果包含笔记信息
        """
        logger.info(f"开始搜索小红书笔记-get_note_all_comment: {note_url}",extra=log_extra)
        
        # note_url = r'https://www.xiaohongshu.com/explore/6824a2aa000000000f03a916?xsec_token=YBjpTNSB7OwG_Q9055_0PqwSPqZsFEHNVBbh81qN6xJZg%3D&xsec_source=pc_creatormng'
        success, msg, note_all_comment = self.xhs_apis.get_note_all_comment(note_url, self.cookies_str)
        return success, msg, note_all_comment



    async def async_get_user_info(self, user_id: str,log_extra:Dict[str, Any]) -> Dict[str, Any]:
        """
        异步获取小红书用户信息
        """

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_user_info, user_id,log_extra)

    def get_user_info(self, user_id: str,log_extra:Dict[str, Any]) -> Dict[str, Any]:
        """
        获取小红书用户信息

        Args:
            user_id: 小红书用户ID或URL

        Returns:
            Dict[str, Any]: 用户信息，包含昵称、关注数、粉丝数等

        Raises:
            XHSError: 处理过程中出现的错误
        """
        logger.info(f"开始小红书--get_user_info: {user_id}")

        success, msg, res_json = self.xhs_apis.get_user_info(user_id, self.cookies_str)
        logger.debug(f"小红书--get_user_info: {success}, {msg}, {res_json}",extra=log_extra)
        
        return res_json

    
    async def async_get_user_post_note(self, user_url: str,log_extra:Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        异步获取小红书用户发布的信息
        """

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_user_post_note, user_url,log_extra)

    def get_user_post_note(self, user_url: str,log_extra:Dict[str, Any]) -> List[Dict[str, Any]]:
        logger.info(f"开始小红书--get_user_post_note: {user_url}")

        success, msg, note_list = self.xhs_apis.get_user_all_notes(user_url, self.cookies_str)
        logger.debug(f"小红书--get_user_info: {success}, {msg}, {note_list}",extra=log_extra)
        
        return note_list

