# bot_api_v1/app/api/routers/media.py

from typing import Dict, Any, Optional, Union # 添加 Union
from datetime import datetime
import uuid
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status, Response # 导入 Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, HttpUrl, validator, Field
from celery.result import AsyncResult # 导入 AsyncResult

# 核心与上下文
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse, MediaContentResponse, RequestContext
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.signature import require_signature # 如果还需要同步路径的签名

# 数据库
from bot_api_v1.app.db.session import get_db

# 服务与工具
from bot_api_v1.app.services.business.media_service import MediaService, MediaError, MediaPlatform # 导入平台
from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
from bot_api_v1.app.utils.decorators.auth_key_checker import require_auth_key
from bot_api_v1.app.utils.decorators.auth_feishu_sheet import require_feishu_signature

# Celery 相关导入
from bot_api_v1.app.tasks.celery_adapter import register_task, get_task_status # 导入适配器函数
from bot_api_v1.app.tasks.celery_tasks import run_media_extraction_new # 导入新的 Celery Task
from bot_api_v1.app.tasks.celery_app import celery_app # 导入 celery_app 实例 (用于 AsyncResult)


# --- 请求与响应模型 ---

class MediaExtractRequest(BaseModel):
    """媒体内容提取请求模型"""
    url: HttpUrl = Field(..., description="媒体URL地址")
    extract_text: bool = Field(True, description="是否提取文案内容")
    include_comments: bool = Field(False, description="是否包含评论数据")

    @validator('url')
    def validate_url(cls, v):
        if not str(v).startswith(('http://', 'https://')):
            raise ValueError('必须是有效的HTTP或HTTPS URL')
        return str(v)

class MediaExtractSubmitResponse(BaseModel):
    """提交异步提取任务后的响应模型"""
    code: int = 202
    message: str
    task_id: str
    request_context: RequestContext

class MediaExtractResponse(BaseModel): # 复用或重命名旧的响应模型
    """提取媒体内容（同步或完成后）的响应模型"""
    code: int = 200
    message: str
    data: Optional[MediaContentResponse] = None # MediaContentResponse 需已定义
    request_context: RequestContext

class MediaExtractStatusResponse(BaseModel):
    """查询异步提取任务状态的响应模型"""
    code: int
    message: str
    task_id: str
    status: str # PENDING, running, completed, failed, cancelled, ...
    result: Optional[MediaContentResponse] = None # 任务成功时的结果
    data: Optional[MediaContentResponse] = None # MediaContentResponse 需已定义
    error: Optional[str] = None # 任务失败时的错误信息
    request_context: RequestContext


# --- 路由 ---

router = APIRouter(prefix="/media", tags=["媒体服务"])

# 实例化服务 (如果还需要调用 identify_platform 或 extract_text=False 的逻辑)
media_service = MediaService()

# clean_url 函数 (保持不变)
async def clean_url(text: str) -> Optional[str]:
    # ... (代码同前) ...
    try:
        if not text:
            logger.warning("收到空的URL文本")
            return None
        url_regex = r'https?://(?:[-\w.]|[?=&/%#])+'
        matches = re.findall(url_regex, str(text))
        if not matches:
            logger.warning(f"未找到有效的URL: {text}")
            return None
        url = matches[0].strip()
        url = re.sub(r'[<>"{}|\\\'^`]', '', url)
        if not url.startswith(('http://', 'https://')):
            logger.warning(f"URL协议不支持: {url}")
            return None
        return url
    except Exception as e:
        logger.error(f"URL提取失败: {str(e)}", exc_info=True)
        return None


# --- 修改后的 /extract 端点 ---
@router.post(
    "/extract",
    # 由于响应模型根据输入动态变化，这里不显式指定 response_model
    # 或者使用更复杂的 Union 类型，但 OpenAPI 可能不支持很好
    # 将在代码中根据情况返回不同模型和状态码
    summary="提取媒体内容(智能同步/异步)", # 添加 summary
    description="如果 extract_text=false，同步返回基础信息(200 OK)。如果 extract_text=true，提交异步任务并返回任务ID(202 Accepted)。",
    tags=["媒体服务"]
)
@TollgateConfig(title="提取媒体内容(智能同步/异步)", type="media", base_tollgate="10", current_tollgate="1", plat="api")
@require_feishu_signature()
@require_auth_key()
async def extract_media_content_smart(
    request: Request,
    extract_request: MediaExtractRequest,
    db: AsyncSession = Depends(get_db) # 保留 DB 依赖，因为同步路径和状态更新可能需要
):
    """
    提取媒体内容信息。
    如果 extract_text=False，同步返回基础信息。
    如果 extract_text=True，提交异步任务并返回任务ID。
    """
    # 优先使用请求上下文，提供默认值
    trace_key = request_ctx.get_trace_key()
    app_id = request_ctx.get_app_id()
    source = request_ctx.get_source()
    user_id = request_ctx.get_user_id()
    user_name = request_ctx.get_user_name()
    ip_address = request.client.host if request.client else "unknown_ip"

    request_context = RequestContext(
        trace_id=trace_key, app_id=app_id, source=source, user_id=user_id,
        user_name=user_name, ip=ip_address, timestamp=datetime.now()
    )
    log_extra = {"request_id": trace_key, "user_id": user_id, "app_id": app_id}

    logger.info(
        f"接收媒体提取请求(Smart): url={extract_request.url}, extract_text={extract_request.extract_text}",
        extra=log_extra
    )

    cleaned_url = await clean_url(extract_request.url)
    if not cleaned_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的URL地址或URL格式不正确")

    # --- 根据 extract_text 决定流程 ---
    if not extract_request.extract_text:
        # --- 旧通道：同步执行 ---
        logger.info("执行同步提取 (extract_text=False)", extra=log_extra)
        try:
            # 调用现有的 MediaService 方法 (假设它在 extract_text=False 时足够快)
            media_content = await media_service.extract_media_content(
                 url=cleaned_url,
                 extract_text=False, # 显式传递 False
                 include_comments=extract_request.include_comments
             )

            response_data = MediaExtractResponse(
                code=200,
                message="成功提取媒体基础信息",
                data=MediaContentResponse(**media_content) if media_content else None,
                request_context=request_context
            )
            # 返回标准的 200 OK 响应
            return response_data

        except Exception as e:
            logger.error(f"同步提取媒体基础信息失败: {str(e)}", exc_info=True, extra=log_extra)
            status_code = 404 if isinstance(e, MediaError) else 500
            detail = f"无法提取媒体内容: {str(e)}" if isinstance(e, MediaError) else f"处理请求时发生错误: {str(e)}"
            raise HTTPException(status_code=status_code, detail=detail)

    else:
        # --- 新通道：提交异步任务 ---
        logger.info("提交异步提取任务 (extract_text=True)", extra=log_extra)
        try:
            platform = media_service.identify_platform(cleaned_url)
            if platform == MediaPlatform.UNKNOWN:
                 raise HTTPException(status_code=400, detail=f"无法识别或不支持的URL平台: {cleaned_url}")

            # !! 调用 celery_adapter 提交新任务 !!
            task_id = register_task(
                name=f"extract_media_{user_id}_{cleaned_url[:20]}",
                task_func=run_media_extraction_new, # 使用新的 Celery Task
                args=( # 显式传递所有需要的参数
                    cleaned_url,
                    True, # extract_text is True
                    extract_request.include_comments,
                    platform,
                    user_id,
                    trace_key, # 传递 trace_id
                    app_id   # 传递 app_id
                    # 如果需要，传递积分信息: initial_points_info=...
                ),
                task_type="media_extraction" # 可以指定队列
            )

            if not task_id:
                 logger.error("提交 Celery 任务失败。", extra=log_extra)
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="无法提交后台处理任务，请稍后重试。")

            # 返回 202 Accepted 响应
            response_data = MediaExtractSubmitResponse(
                code=202,
                message="提取任务已提交，正在后台处理中。",
                task_id=task_id,
                request_context=request_context
            )
            # 需要使用 Response 类来设置正确的状态码
            return Response(
                 content=response_data.model_dump_json(), # 使用 Pydantic V2 的方法
                 status_code=status.HTTP_202_ACCEPTED,
                 media_type="application/json"
            )

        except HTTPException as e:
             raise e # 直接抛出已知的 HTTP 异常
        except Exception as e:
            logger.error(f"提交异步媒体提取任务时发生未知错误: {str(e)}", exc_info=True, extra=log_extra)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"提交任务时发生未知错误 ({trace_key})")


# --- 新的状态查询端点 ---
@router.get(
    "/extract/status/{task_id}",
    response_model=MediaExtractStatusResponse,
    summary="查询媒体提取任务状态和结果",
    tags=["媒体服务"]
)
@TollgateConfig(title="获取提取媒体内容的任务执行结果", type="media", base_tollgate="10", current_tollgate="1", plat="api")
@require_feishu_signature()
@require_auth_key() # 添加必要的认证
async def get_extract_media_status(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db) # 依赖注入 DB Session，用于后续写库
):
    """根据任务ID查询异步媒体提取任务的状态和结果。"""
    trace_key = request_ctx.get_trace_key()
    app_id = request_ctx.get_app_id()
    source = request_ctx.get_source()
    user_id = request_ctx.get_user_id()
    user_name = request_ctx.get_user_name()
    ip_address = request.client.host if request.client else "unknown_ip"
    
    log_extra = {"request_id": trace_key, "celery_task_id": task_id, "user_id": user_id}
    logger.info(f"查询任务状态: {task_id}", extra=log_extra)

    # 1. 调用适配器获取基本状态
    task_info = await get_task_status(task_id) # 使用 celery_adapter 中的函数

    if not task_info or task_info.get("status") == "error_fetching_status":
        logger.warning(f"未找到任务或获取状态失败: {task_id}", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"任务 ID '{task_id}' 不存在或状态获取失败。")

    current_status = task_info.get("status", "unknown")
    error_message = task_info.get("error")
    task_result_data = None
    response_code = 202
    response_message = f"任务状态: {current_status}"

    # 2. 如果任务可能已完成，尝试获取详细结果
    if current_status in ["completed", "failed"]:
        try:
            result_obj = AsyncResult(task_id, app=celery_app)
            if result_obj.ready(): # 再次确认任务已就绪（完成或失败）
                if result_obj.successful():
                    task_return_value = result_obj.result # 获取 Celery Task 的返回值
                    if isinstance(task_return_value, dict):
                        task_logic_status = task_return_value.get("status")
                        if task_logic_status == "success":
                            # ---- 任务成功完成 ----
                            current_status = "completed" # 确认最终状态
                            media_data = task_return_value.get("data")
                            points_consumed = task_return_value.get("points_consumed", 0)
                            
                            # logger.info(f"task_return_value is {task_return_value}", extra=log_extra)
                            # logger.info(f"points_consumed is {points_consumed}", extra=log_extra)
                            # logger.info(f"media_data is {media_data}", extra=log_extra)

                            # 尝试构建 MediaContentResponse
                            try:
                                # 在构建 MediaContentResponse 前处理数据
                                if media_data:
                                    # 使用 MediaService 的静态方法转换数据格式
                                    media_data = MediaService.convert_to_standard_format(media_data)
                                
                                # 现在尝试构建响应
                                task_result_data = MediaContentResponse(**media_data) if media_data else None
                                response_code=200
                                response_message = task_return_value.get("message", "任务成功完成")
                            except Exception as parse_err:
                                logger.error(f"解析任务 {task_id} 成功结果中的 data 失败: {parse_err}", extra=log_extra)
                                # 记录详细的数据结构以便调试
                                logger.debug(f"媒体数据结构: {media_data}", extra=log_extra)
                                current_status = "failed" # 任务成功但结果解析失败，标记为失败
                                error_message = f"任务成功，但结果解析失败: {str(parse_err)}"
                                response_code = 500

                            # ---- 在这里执行数据库写入操作 ----
                            if current_status == "completed" and points_consumed > 0:
                                logger.info(f"任务 {task_id} 成功完成，准备扣除积分: {points_consumed}", extra=log_extra)
                                try:
                                    # !! 需要实现扣除积分的逻辑 !!
                                    # task_user_id = ... # 需要从某处获取任务发起者的 user_id (可能需要 Celery Task 返回)
                                    # success = await deduct_points(db, task_user_id, points_consumed, task_id)
                                    # if not success: logger.warning(...)
                                    request_ctx.set_consumed_points(points_consumed) # 更新请求上下文
                                    logger.info(f"填充消耗 {points_consumed} 积分", extra=log_extra) # Placeholder
                                    pass # Placeholder for DB write
                                except Exception as db_err:
                                     logger.error(f"任务 {task_id} 成功后扣除积分失败: {db_err}", exc_info=True, extra=log_extra)
                                     # 考虑如何处理：积分未扣除，但任务已完成？
                                     # 可以附加警告信息到响应中
                                     response_message += " (警告: 积分扣除可能失败)"
                            
                            # ---- 在这里可以保存结果到数据库 (如果需要) ----
                            # try:
                            #    await save_extraction_result(db, task_id, task_result_data)
                            # except Exception as save_err: ...

                        elif task_logic_status == "failed":
                             # ---- 任务内部逻辑失败 ----
                             current_status = "failed"
                             error_message = task_return_value.get("error", "任务报告失败，但未提供错误信息")
                             response_message = error_message
                             response_code = 500 # 或其他合适的状态码
                             logger.error(f"任务 {task_id} 内部逻辑失败: {error_message}", extra=log_extra)
                        else:
                             # 任务成功返回，但 status 字段未知
                             logger.error(f"任务 {task_id} 成功返回，但结果字典状态未知: {task_logic_status}", extra=log_extra)
                             response_message = "任务完成，但结果状态未知"
                             # 也许可以尝试解析 data
                             media_data = task_return_value.get("data")
                             try:
                                 task_result_data = MediaContentResponse(**media_data) if media_data else None
                             except: pass # 忽略解析错误
                    else:
                         # 任务成功，但返回值不是预期的字典格式
                         current_status = "failed" # 视为一种失败
                         error_message = "任务成功，但返回结果格式不正确"
                         response_message = error_message
                         response_code = 500
                         logger.error(f"任务 {task_id} 成功，但返回值格式非预期: {type(task_return_value)}", extra=log_extra)

                elif result_obj.failed():
                    # ---- Celery 层面标记为失败 ----
                    current_status = "failed"
                    if not error_message: # 如果 get_task_status 没获取到错误
                        error_message = str(result_obj.info) if result_obj.info else "任务失败，未知错误"
                    response_message = error_message
                    response_code = 500
                    logger.error(f"任务 {task_id} 在 Celery 中标记为失败: {error_message}", extra=log_extra)
            else:
                 # 任务状态是 completed/failed，但 result_obj 说还没 ready？不太可能，记录一下
                 logger.warning(f"任务 {task_id} 状态为 {current_status} 但 AsyncResult is not ready()", extra=log_extra)

        except Exception as e:
            logger.error(f"获取或解析任务 {task_id} 详细结果时出错: {e}", exc_info=True, extra=log_extra)
            # 保留从 get_task_status 获取的基本状态信息
            if current_status not in ["failed", "cancelled", "error_fetching_status"]:
                current_status = "unknown_error" # 表示获取结果阶段出错
            if not error_message:
                error_message = f"查询任务结果时发生内部错误 ({trace_key})"
            response_message = error_message

    # 构建请求上下文 (用于响应)
    request_context = RequestContext(
        trace_id=trace_key, app_id=app_id, source=source, user_id=user_id,
        user_name=user_name, ip=ip_address, timestamp=datetime.now()
    )

    # 构建最终响应
    final_response = MediaExtractStatusResponse(
        code=response_code,
        message=response_message,
        task_id=task_id,
        status=current_status,
        result=task_result_data, # 成功时才有数据
        data=task_result_data,
        error=error_message if current_status == "failed" else None, # 失败时才有错误
        request_context=request_context
    )

    # 对于仍在运行的状态，可以考虑返回 200 OK，让客户端继续轮询
    # 对于最终状态 (completed/failed)，也返回 200 OK
    return final_response





# ... 现有代码 ...

# --- 新增测试端点 ---
@router.get(
    "/test/xhs_sync",
    summary="测试小红书同步提取方法",
    description="测试 XHSService 的 get_note_info_sync_for_celery 方法，用于 Celery 任务开发",
    tags=["媒体服务-测试"]
)
async def test_xhs_sync_method(
    request: Request,
    # url: str = "https://www.xiaohongshu.com/explore/67e2b3f900000000030286ce?xsec_token=ABsttmnMANeopanZhB7mwrTWl3izLUb0_nFBSUxqS4EZk=&xsec_source=pc_feed",
    url: str = "https://v.douyin.com/YX-HGKSVNzU/",
    extract_text: bool = True
):
    """
    测试 XHSService 的同步方法，用于 Celery 任务开发
    """
    # 获取基本信息
    trace_key = request_ctx.get_trace_key() or str(uuid.uuid4())
    user_id = request_ctx.get_user_id() or "test_user"
    
    # 实例化 XHSService
    from bot_api_v1.app.services.business.xhs_service import XHSService
    xhs_service = XHSService()
    
    try:
        # 调用同步方法
        # result = xhs_service.get_note_info_sync_for_celery(
        #     url=url,
        #     extract_text=extract_text,
        #     user_id_for_points=user_id,
        #     trace_id=trace_key
        # )

        from bot_api_v1.app.services.business.tiktok_service import TikTokService
        tiktok_service = TikTokService()
        result = tiktok_service.get_video_info_sync_for_celery(
            url=url,
            extract_text=extract_text,
            user_id_for_points=user_id,
            trace_id=trace_key
        )
        
        # 返回结果
        return {
            "code": 200,
            "message": "测试成功",
            "test_result": result,
            "request_context": {
                "trace_id": trace_key,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"测试 XHSService 同步方法失败: {str(e)}", exc_info=True)
        return {
            "code": 500,
            "message": f"测试失败: {str(e)}",
            "request_context": {
                "trace_id": trace_key,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }
        }

# ... 现有代码继续 ...