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
    """
    (V4 重写) 根据 Task A ID 查询状态。
    检查 Task A 返回值中的内部状态，决定是否查询 Task B 并聚合结果。
    """
    # 1. 初始化上下文和日志
    try:
        trace_key = request_ctx.get_trace_key()
        app_id = request_ctx.get_app_id()
        source = request_ctx.get_source()
        user_id = request_ctx.get_user_id()
        user_name = request_ctx.get_user_name()
        ip_address = request.client.host if request.client else "unknown_ip"
        log_extra = {"request_id": trace_key, "celery_task_id": task_id, "user_id": user_id}
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
                     # Task A 直接成功完成 (例如 extract_text=False)
                     final_task_status = "completed"
                     media_data_dict = result_A_data.get("data")
                     points_consumed = result_A_data.get("points_consumed", 0)
                     response_message = result_A_data.get("message", "任务成功完成")
                     try:
                         # 转换并验证 Pydantic 模型
                         if media_data_dict:
                             media_data_dict = MediaService.convert_to_standard_format(media_data_dict)
                             response_data = MediaContentResponse(**media_data_dict)
                         request_ctx.set_consumed_points(points_consumed) # 设置积分
                         # await deduct_points(...)
                     except Exception as parse_err:
                         logger.error(f"解析 Task A ({task_id}) 直接成功结果失败: {parse_err}", exc_info=True, extra=log_extra)
                         final_task_status = "failed"
                         response_error_msg = f"任务成功但结果解析失败: {parse_err}"
                         response_message = response_error_msg

                 elif task_A_internal_status == 'processing':
                     # Task A 成功触发 Task B，需要查询 Task B
                     final_task_status = "transcribing" # 初始为转写中
                     response_status_code = status.HTTP_202_ACCEPTED
                     response_message = "正在进行语音转写..."

                     task_b_id = result_A_data.get('transcription_task_id')
                     basic_info = result_A_data.get('basic_info')
                     base_points = result_A_data.get('base_points', 0)

                     if task_b_id and isinstance(basic_info, dict):
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
                                 transcribed_text = result_B_data.get("text") # 直接获取 text
                                 transcription_points = result_B_data.get("points_consumed", 0)
                                 points_consumed = base_points + transcription_points
                                 # 合并结果
                                 final_combined_data = {**basic_info, "content": transcribed_text}
                                 try:
                                     # 转换并验证
                                     final_combined_data = MediaService.convert_to_standard_format(final_combined_data)
                                     response_data = MediaContentResponse(**final_combined_data)
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
        status=final_task_status, # 使用处理后的最终状态字符串
        data=response_data, # 成功时的数据
        error=response_error_msg if final_task_status == "failed" else None, # 失败时的错误信息
        request_context=request_context
    )

    logger.debug(f"查询任务状态 (V4) 完成,final check final_response_obj is : {final_response_obj}", extra=log_extra)

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