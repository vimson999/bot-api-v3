# bot_api_v1/app/api/routers/media.py

from typing import Dict, Any, Optional, Union # 添加 Union
from datetime import datetime
import uuid
import re
import traceback
from bot_api_v1.app.core.cache import RedisCache

import httpx
from fastapi import Header

from fastapi import APIRouter, Depends, HTTPException, Request, status, Response # 导入 Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, HttpUrl, validator, Field
from celery.result import AsyncResult # 导入 AsyncResult

# 核心与上下文
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse, MediaContentResponse, RequestContext
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.signature import require_signature # 如果还需要同步路径的签名
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format

# 数据库
from bot_api_v1.app.db.session import get_db

# 服务与工具
from bot_api_v1.app.services.business.media_service import MediaService, MediaError # 导入平台
from bot_api_v1.app.constants.media_info import MediaPlatform


from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
from bot_api_v1.app.utils.decorators.api_refer import require_api_security ,decrypt_and_validate_request
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
    root_trace_key: str
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
    root_trace_key: str
    status: str # PENDING, running, completed, failed, cancelled, ...
    result: Optional[MediaContentResponse] = None # 任务成功时的结果
    data: Optional[MediaContentResponse] = None # MediaContentResponse 需已定义
    error: Optional[str] = None # 任务失败时的错误信息
    request_context: RequestContext


# --- 路由 ---

router = APIRouter(prefix="/media", tags=["媒体服务"])

# 实例化服务 (如果还需要调用 identify_platform 或 extract_text=False 的逻辑)
media_service = MediaService()
media_extract_format = Media_extract_format() # 实例化 Media_extract_format

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



# 公共方法
async def _extract_media_content_common(
    request: Request,
    extract_request: MediaExtractRequest,
    db: AsyncSession,
    require_feishu_sign: bool = True
):
    """
    提取媒体内容信息的公共方法。
    require_feishu_sign: 是否需要校验飞书签名（仅用于日志/上下文区分）
    """
    # 优先使用请求上下文，提供默认值
    trace_key = request_ctx.get_trace_key()
    app_id = request_ctx.get_app_id()
    source = request_ctx.get_source()
    user_id = request_ctx.get_cappa_user_id()
    user_name = request_ctx.get_user_name()
    ip_address = request.client.host if request.client else "unknown_ip"
    root_trace_key = request_ctx.get_root_trace_key()

    request_context = RequestContext(
        trace_id=trace_key, app_id=app_id, source=source, user_id=user_id,
        user_name=user_name, ip=ip_address, timestamp=datetime.now()
    )
    log_extra = {"request_id": trace_key, "user_id": user_id, "app_id": app_id, "root_trace_key": root_trace_key, "feishu_sign": require_feishu_sign}

    logger.info_to_db(
        f"接收媒体提取请求(Smart) begin: url={extract_request.url}, extract_text={extract_request.extract_text}",
        extra=log_extra
    )

    cleaned_url = await clean_url(extract_request.url)
    if not cleaned_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的URL地址或URL格式不正确")

    # --- 根据 extract_text 决定流程 ---
    if not extract_request.extract_text:
        # --- 旧通道：同步执行 ---
        logger.debug("不抓文案只抓基本信息,执行同步提取 (extract_text=False)", extra=log_extra)
        try:
            media_content = await media_service.extract_media_content(
                url=cleaned_url,
                extract_text=False,
                include_comments=extract_request.include_comments
            )
            response_data = MediaExtractResponse(
                code=200,
                message="成功提取媒体基础信息",
                data=MediaContentResponse(**media_content) if media_content else None,
                request_context=request_context
            )
            logger.debug("不抓文案只抓基本信息,执行同步提取 (extract_text=False)结束,response_data is {response_data}", extra=log_extra)
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
            platform = media_extract_format._identify_platform(cleaned_url)
            if platform == MediaPlatform.UNKNOWN:
                raise HTTPException(status_code=400, detail=f"无法识别或不支持的URL平台: {cleaned_url}")

            task_type = "media_extraction"
            if platform in [MediaPlatform.YOUTUBE, MediaPlatform.TIKTOK, MediaPlatform.INSTAGRAM, MediaPlatform.TWITTER]:
                task_type = "bad_news"

            task_id = register_task(
                name=f"extract_media_{user_id}_{cleaned_url[:20]}",
                task_func=run_media_extraction_new,
                args=(
                    cleaned_url,
                    True,
                    extract_request.include_comments,
                    platform,
                    user_id,
                    trace_key,
                    app_id,
                    root_trace_key,
                    require_feishu_sign
                ),
                task_type=task_type
            )

            if not task_id:
                logger.error("提交 Celery 任务失败。", extra=log_extra)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="无法提交后台处理任务，请稍后重试。")

            response_data = MediaExtractSubmitResponse(
                code=202,
                message="提取任务已提交，正在后台处理中。",
                task_id=task_id,
                root_trace_key=root_trace_key,
                request_context=request_context
            )
            return Response(
                content=response_data.model_dump_json(),
                status_code=status.HTTP_202_ACCEPTED,
                media_type="application/json"
            )
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"提交异步媒体提取任务时发生未知错误: {str(e)}", exc_info=True, extra=log_extra)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"提交任务时发生未知错误 ({trace_key})")


@router.post(
    "/extract/coze",
    summary="提取媒体内容(无飞书签名校验)",
    description="不校验飞书签名，适用于内部或特殊场景。",
    tags=["媒体服务"]
)
@TollgateConfig(title="提取媒体内容(无飞书签名校验)", type="media", base_tollgate="10", current_tollgate="1", plat="api")
@require_auth_key()
async def extract_media_content_no_feishu(
    request: Request,
    extract_request: MediaExtractRequest,
    db: AsyncSession = Depends(get_db)
):
    return await _extract_media_content_common(request, extract_request, db, require_feishu_sign=False)

# 原有接口，保留飞书签名校验
@router.post(
    "/extract",
    summary="提取媒体内容(智能同步/异步)",
    description="如果 extract_text=false，同步返回基础信息(200 OK)。如果 extract_text=true，提交异步任务并返回任务ID(202 Accepted)。",
    tags=["媒体服务"]
)
@TollgateConfig(title="提取媒体内容(智能同步/异步)", type="media", base_tollgate="10", current_tollgate="1", plat="api")
@require_feishu_signature()
@require_auth_key()
async def extract_media_content_smart(
    request: Request,
    extract_request: MediaExtractRequest,
    db: AsyncSession = Depends(get_db)
):
    return await _extract_media_content_common(request, extract_request, db, require_feishu_sign=True)




async def task_A_running():
    final_task_status = "running"
    response_status_code = status.HTTP_202_ACCEPTED
    response_message = "任务正在处理中..."

    return final_task_status, response_status_code, response_message


async def _get_extract_media_status_common(
    task_id: str,
    request: Request,
    db: AsyncSession,
    require_feishu_sign: bool = True
):
    """
    (V4 重写) 根据 Task A ID 查询状态。
    检查 Task A 返回值中的内部状态，决定是否查询 Task B 并聚合结果。
    """
    # 1. 初始化上下文和日志
    try:
        trace_key = request_ctx.get_trace_key()
        app_id = request_ctx.get_app_id()
        source = request_ctx.get_source()
        user_id = request_ctx.get_cappa_user_id()
        user_name = request_ctx.get_user_name()
        ip_address = request.client.host if request.client else "unknown_ip"
        root_trace_key = request_ctx.get_root_trace_key()
        platform = 'platform'
        log_extra = {"request_id": trace_key, "celery_task_id": task_id, "user_id": user_id,"root_trace_key":root_trace_key,"platform":platform}
    except Exception as ctx_err:
        # 如果连上下文都获取失败，记录严重错误并返回
        logger.critical(f"获取请求上下文失败: {ctx_err}", exc_info=True)
        raise HTTPException(status_code=500, detail="无法处理请求上下文")

    logger.info(f"查询任务状态 (V4): {task_id}", extra=log_extra)

    # 构建 request_context 对象 (如果获取成功)
    request_context = RequestContext(
        trace_id=trace_key, app_id=app_id, source=source, user_id=user_id,
        user_name=user_name, ip=ip_address, timestamp=datetime.now()
    )

    # 初始化默认响应值
    response_status_code = status.HTTP_200_OK # 默认查询成功
    response_data = None
    response_error_msg = None
    final_task_status = "unknown" # 返回给客户端的状态
    response_message = "任务状态未知"
    points_consumed = 0

    try:
        # 2. 查询 Task A
        result_A = AsyncResult(task_id, app=celery_app)
        status_A = result_A.state
        result_A_data = result_A.result # Task A 返回值
        info_A = result_A.info # Task A 失败时的信息 (或 meta)

        logger.debug(f"Task A ({task_id}) Status: {status_A}, Result: {result_A_data}, Info: {info_A}", extra=log_extra)

        # 3. 处理 Task A 状态
        if status_A in ('PENDING', 'STARTED', 'RETRY'):
            # final_task_status,response_status_code ,response_message = task_A_running()
            final_task_status = "running"
            response_status_code = status.HTTP_202_ACCEPTED
            response_message = "任务正在处理中..."

        elif status_A == 'FAILURE':
            final_task_status = "failed"
            if isinstance(info_A, dict):
                response_error_msg = info_A.get("error", "任务执行失败")
                points_consumed = info_A.get("points_consumed", 0) # 通常为0
            else:
                response_error_msg = str(info_A or "任务执行失败")
            response_message = response_error_msg
            logger.error(f"Task A ({task_id}) 失败: {response_error_msg}", extra=log_extra)

        elif status_A == 'SUCCESS':
            # Task A 执行完成，需要检查其返回值 result_A_data
            if not isinstance(result_A_data, dict):
                 # Task A 成功了但返回值不是预期的字典 (例如返回了 None?)
                 final_task_status = "failed"
                 response_error_msg = "任务结果格式异常 (非字典)"
                 response_message = response_error_msg
                 logger.error(f"Task A ({task_id}) 状态 SUCCESS 但 result 非字典: {type(result_A_data)}", extra=log_extra)
            else:
                 # Task A 返回值是字典，检查内部状态
                 task_A_internal_status = result_A_data.get('status')

                 if task_A_internal_status == 'success':
                     final_task_status = "completed"
                     final_combined_data = result_A_data.get("data")
                     points_consumed = result_A_data.get("points_consumed", 0)
                     try:
                        response_data = MediaContentResponse(**final_combined_data) if final_combined_data else None
                        response_message = result_A_data.get("message", "提取和转写成功完成")
                        request_ctx.set_consumed_points(points_consumed)
                        response_status_code = status.HTTP_200_OK
                     except Exception as parse_err:
                        logger.error(f"从Task A ({task_id}) 成功结果直接拉取时，失败: {parse_err}", exc_info=True, extra=log_extra)
                        final_task_status = "failed"
                        response_error_msg = f"task A任务成功,但结果拉取时解析失败: {parse_err}"
                        response_message = response_error_msg
                 elif task_A_internal_status == 'processing':
                     # Task A 成功触发 Task B，需要查询 Task B
                     final_task_status = "transcribing" # 初始为转写中
                     response_status_code = status.HTTP_202_ACCEPTED
                     response_message = "正在进行语音转写..."

                     task_b_id = result_A_data.get('transcription_task_id')
                     base_points = result_A_data.get('base_points', 10)

                     if task_b_id :
                         # 查询 Task B
                         result_B = AsyncResult(task_b_id, app=celery_app)
                         status_B = result_B.state
                         result_B_data = result_B.result if status_B == 'SUCCESS' else result_B.info
                         logger.debug(f"Task B ({task_b_id}) Status: {status_B}, Result/Info: {result_B_data}", extra=log_extra)

                         if status_B == 'SUCCESS':
                             # Task B 成功
                             if isinstance(result_B_data, dict) and result_B_data.get("status") == "success":
                                 final_task_status = "completed"
                                 response_status_code = status.HTTP_200_OK

                                 final_combined_data = result_B_data.get("data")
                                 points_consumed = result_B_data.get("points_consumed", 0)
                                 try:
                                     response_data = MediaContentResponse(**final_combined_data) if final_combined_data else None
                                     response_message = result_B_data.get("message", "提取和转写成功完成")
                                     request_ctx.set_consumed_points(points_consumed)
                                     # await deduct_points(...)
                                 except Exception as parse_err:
                                     logger.error(f"合并或解析 Task B ({task_b_id}) 成功结果失败: {parse_err}", exc_info=True, extra=log_extra)
                                     final_task_status = "failed"
                                     response_error_msg = f"任务成功但结果合并或解析失败: {parse_err}"
                                     response_message = response_error_msg
                             else:
                                 # Task B 状态 SUCCESS 但结果字典内部状态不对
                                 logger.error(f"Task B ({task_b_id}) SUCCESS 但结果内容异常: {result_B_data}", extra=log_extra)
                                 final_task_status = "failed"
                                 response_error_msg = "转写任务结果内容异常"
                                 response_message = response_error_msg
                                 points_consumed = base_points # 只计算基础分
                                 try: # 尝试返回基础信息
                                     response_data = MediaContentResponse(**basic_info) if basic_info else None
                                 except: pass

                         elif status_B == 'FAILURE':
                             # Task B 失败
                             final_task_status = "failed"
                             response_status_code = status.HTTP_200_OK # 查询成功，但任务失败
                             points_consumed = base_points
                             if isinstance(result_B_data, dict): # 错误信息在 meta (info)
                                 response_error_msg = result_B_data.get("error", "转写任务失败")
                             else:
                                 response_error_msg = str(result_B_data or "转写任务失败")
                             response_message = response_error_msg
                             logger.error(f"Task B ({task_b_id}) 失败: {response_error_msg}", extra=log_extra)
                             try: # 尝试返回基础信息
                                 response_data = MediaContentResponse(**basic_info) if basic_info else None
                             except: pass
                         else:
                             # Task B 仍在运行 PENDING/STARTED/RETRY
                             # 保持 transcribing / 202 状态
                             pass
                     else:
                         # Task A 返回 processing 但缺少 task_b_id 或 basic_info
                         logger.error(f"Task A ({task_id}) 返回 processing 但关键信息丢失!", extra=log_extra)
                         final_task_status = "failed"
                         response_error_msg = "内部错误：任务状态协调失败"
                         response_message = response_error_msg

                 elif task_A_internal_status == 'failed':
                      # Task A 返回的字典表明准备阶段就失败了
                      final_task_status = "failed"
                      response_error_msg = result_A_data.get("error", "任务准备阶段失败")
                      points_consumed = result_A_data.get("points_consumed", 0)
                      response_message = response_error_msg
                      logger.error(f"Task A ({task_id}) 内部逻辑标记失败: {response_error_msg}", extra=log_extra)
                 else:
                      # Task A 返回字典，但内部 status 未知
                      final_task_status = "failed"
                      response_error_msg = f"任务结果内部状态未知: {task_A_internal_status}"
                      response_message = response_error_msg
                      logger.error(f"Task A ({task_id}) SUCCESS 但结果内部状态未知: {task_A_internal_status}", extra=log_extra)

        else: # 其他未知或不应出现的 Celery 状态 (如 REVOKED)
            final_task_status = status_A # 直接使用 Celery 状态
            response_error_msg = f"任务处于非预期状态: {status_A}"
            response_message = response_error_msg
            logger.warning(f"Task A ({task_id}) 处于非预期状态: {status_A}", extra=log_extra)

    except Exception as e:
        # 捕获查询过程中的任何其他异常
        logger.error(f"查询任务 {task_id} 状态时发生不可预知错误: {e}", exc_info=True, extra=log_extra)
        final_task_status = "failed"
        # 使用 traceback 记录更详细的错误用于调试
        response_error_msg = f"查询任务状态时发生内部错误: {e}\n{traceback.format_exc()}"
        response_message = f"查询任务状态时发生内部错误 ({trace_key})"
        # 强制返回 500 错误给客户端，而不是 200 OK
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=response_message
        )

    # 4. 构建最终响应模型
    final_response_obj = MediaExtractStatusResponse(
        code=200 if final_task_status == "completed" else (202 if final_task_status in ["running", "transcribing"] else 500), # 映射业务状态码
        message=response_message,
        task_id=task_id,
        root_trace_key=root_trace_key,
        status=final_task_status, # 使用处理后的最终状态字符串
        data=response_data, # 成功时的数据
        error=response_error_msg if final_task_status == "failed" else None, # 失败时的错误信息
        request_context=request_context
    )

    logger.info_to_db(f"查询任务状态 (V4) 完成,final check final_response_obj is : {final_response_obj}", extra=log_extra)
    if ( response_status_code == status.HTTP_200_OK and not response_data ):
        request_ctx.set_consumed_points(0)
        logger.info_to_db(f" 查询任务状态 (V4)这里没有真正拿到返回值 data is null ，因此不能扣分 : {final_response_obj}", extra=log_extra)

    # 5. 返回响应
    if response_status_code == status.HTTP_202_ACCEPTED:
         # 对于处理中的状态，确保不返回 data 和 error
         final_response_obj.data = None
         final_response_obj.error = None
         return Response(
             content=final_response_obj.model_dump_json(exclude_none=True),
             status_code=status.HTTP_202_ACCEPTED,
             media_type="application/json"
         )
    else: # 200 OK (任务完成，无论成功或失败)
         return final_response_obj # FastAPI 会处理序列化


@router.get(
    "/extract/status/{task_id}",
    response_model=MediaExtractStatusResponse,
    summary="查询媒体提取任务状态和结果 (V2 - 聚合模式)", # 更新 summary
    tags=["媒体服务"]
)
@TollgateConfig(title="获取提取媒体内容的任务执行结果", type="media", base_tollgate="10", current_tollgate="1", plat="api")
@require_feishu_signature()
@require_auth_key()
async def get_extract_media_status_v4( # 函数名加后缀以便区分
    task_id: str, # Task A ID
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    return await _get_extract_media_status_common(task_id, request, db, require_feishu_sign=True)


@router.get(
    "/extract/coze/status/{task_id}",
    response_model=MediaExtractStatusResponse,
    summary="查询媒体提取任务状态和结果 (无飞书签名校验)",
    tags=["媒体服务"]
)
@TollgateConfig(title="获取提取媒体内容的任务执行结果(无飞书签名校验)", type="media", base_tollgate="10", current_tollgate="1", plat="api")
@require_auth_key()
async def get_extract_media_status_no_feishu(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    return await _get_extract_media_status_common(task_id, request, db, require_feishu_sign=False)

@router.get("/proxy/vd")
async def proxy_video(url: str):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(url)
        headers = {
            "Content-Type": r.headers.get("Content-Type", "video/mp4"),
            "Access-Control-Allow-Origin": "*"
        }
        return Response(content=r.content, headers=headers)



@router.post(
    "/e1/bsc",
    response_model=MediaExtractResponse,
    summary="同步提取媒体基础信息",
    description="同步提取媒体基础信息（不抓文案，仅基础信息），适合前端直接调用。",
    tags=["媒体服务"]
)
@TollgateConfig(title="不扣分提取接口", type="media", base_tollgate="10", current_tollgate="1", plat="s-site")
@require_api_security()
async def extract_media_basic_info(
    request: Request,
    decrypted_payload: dict = Depends(decrypt_and_validate_request)
):
    """
    处理加密的媒体基础信息提取请求。
    解密和 Ticket 验证由 `decrypt_and_validate_request` 依赖项处理。
    """
    # decrypted_payload 现在包含了解密后的数据，例如: {'url': '...', 'extract_text': False, ...}
    # 现在可以安全地使用它来构造 Pydantic 模型或直接访问
    try:
        # 在函数体内部，使用解密后的字典来创建 Pydantic 模型实例
        extract_request = MediaExtractRequest(**decrypted_payload)
    except Exception as e: # 例如 Pydantic 验证错误
         logger.warning(f"无法将解密后的数据构造成 MediaExtractRequest: {e}, data: {decrypted_payload}")
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="解密后的请求数据格式不正确")



    # --- 从这里开始，逻辑与之前类似，但使用 extract_request ---
    trace_key = request_ctx.get_trace_key()
    app_id = request_ctx.get_app_id()
    source = request_ctx.get_source()
    user_id = request_ctx.get_cappa_user_id()
    user_name = request_ctx.get_user_name()
    ip_address = request.client.host if request.client else "unknown_ip"
    root_trace_key = request_ctx.get_root_trace_key()

    request_context = RequestContext(
        trace_id=trace_key, app_id=app_id, source=source, user_id=user_id,
        user_name=user_name, ip=ip_address, timestamp=datetime.now()
    )
    log_extra = {"request_id": trace_key, "user_id": user_id, "app_id": app_id, "root_trace_key": root_trace_key}

    logger.info_to_db(
        f"不扣分提取接口接收媒体基础信息提取请求 (已解密): url={extract_request.url}",
        extra=log_extra
    )

    cleaned_url = await clean_url(extract_request.url)
    if not cleaned_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的URL地址或URL格式不正确")

    try:
        media_content = await media_service.extract_media_content(
            url=cleaned_url,
            extract_text=False, # 明确指定，不依赖于解密后的请求值（除非需要用户控制）
            include_comments=extract_request.include_comments, # 使用解密后的值
            cal_points = False # 明确指定
        )

        if not media_content: # 如果服务返回 None 或空
             raise MediaError("无法从指定 URL 提取到媒体内容")

        response_data = MediaExtractResponse(
            code=200,
            message="成功提取媒体基础信息",
            # 确保 media_content 是字典或可以解包给 MediaContentResponse
            data=MediaContentResponse(**media_content) if isinstance(media_content, dict) else media_content,
            request_context=request_context
        )
        logger.debug("同步提取媒体基础信息结束", extra=log_extra)
        return response_data

    # **改进**: 更具体的异常处理
    except MediaError as e:
        logger.warning(f"媒体提取失败 (MediaError): {str(e)} for url: {cleaned_url}", extra=log_extra)
        # 对于客户端可预期的错误（如找不到视频），使用 404 或 400
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"无法提取媒体内容: {str(e)}")
    except HTTPException:
        # 重新抛出由 clean_url 或其他地方引发的 HTTPException
        raise
    except Exception as e:
        # 捕获其他所有意外错误
        logger.error(f"处理媒体提取请求时发生意外错误: {str(e)} for url: {cleaned_url}", exc_info=True, extra=log_extra)
        # 对于未知服务器错误，使用 500
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="处理请求时发生内部错误")



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

@router.post(
    "/dc",
    summary="删除缓存",
    tags=["媒体服务"]
)
async def delete_cache(
    url: str
):
    logger.info(f"收到删除缓存请求: url={url}")
    key = RedisCache.create_key("get_task_b_result", url)
    success = RedisCache.del_key(key)
    logger.info(f"收到删除缓存key: key={key}")

    if success:
        return {"code": 200, "message": f"缓存已删除: url={url},key={key}"}
    else:
        return {"code": 500, "message": f"删除缓存失败: url={url},key={key}"}