# bot_api_v1/app/api/routers/media.py

from hashlib import new
from typing import Dict, Any, Optional, Union # 添加 Union
from datetime import datetime
import uuid
import re
import traceback
from bot_api_v1.app.core.cache import RedisCache
from bot_api_v1.app.services.helper.user_profile_helper import UserProfileHelper
from bot_api_v1.app.services.helper.video_comment_helper import VideoCommentHelper
from bot_api_v1.app.services.helper.media_extract_content_helper import MediaExtractContentHelper

import httpx
from fastapi import Header


from fastapi import APIRouter, Depends, HTTPException, Request, status, Response ,Body# 导入 Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, HttpUrl, validator, Field
from celery.result import AsyncResult # 导入 AsyncResult

# 核心与上下文
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse, MediaContentResponse,SearchNoteData,KOLResponse, RequestContext,MediaExtractBasicContentResponse,MediaBasicContentResponse,MediaExtractRequest,MediaExtractStatusResponse,SearchNoteRequest,SearchNoteResponse,SearchNoteDataMediaExtractResponse,MediaExtractSubmitResponse
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
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format

# Celery 相关导入
from bot_api_v1.app.tasks.celery_adapter import register_task, get_task_status # 导入适配器函数
from bot_api_v1.app.tasks.celery_tasks import run_media_extraction_new # 导入新的 Celery Task
from bot_api_v1.app.tasks.celery_app import celery_app # 导入 celery_app 实例 (用于 AsyncResult)


# --- 路由 ---
router = APIRouter(prefix="/media", tags=["媒体服务"])

# 实例化服务 (如果还需要调用 identify_platform 或 extract_text=False 的逻辑)
media_service = MediaService()
media_extract_format = Media_extract_format() # 实例化 Media_extract_format
user_profile_helper = UserProfileHelper()
video_comment_helper = VideoCommentHelper()
media_extract_content_helper = MediaExtractContentHelper()

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
    return await media_extract_content_helper._extract_media_content_common(request, extract_request, db, require_feishu_sign=False)

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
    return await media_extract_content_helper._extract_media_content_common(request, extract_request, db, require_feishu_sign=True)


async def task_A_running():
    final_task_status = "running"
    response_status_code = status.HTTP_202_ACCEPTED
    response_message = "任务正在处理中..."
    return final_task_status, response_status_code, response_message


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
    return await media_extract_content_helper._get_extract_media_status_common(task_id, request, db, require_feishu_sign=True)

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
    return await media_extract_content_helper._get_extract_media_status_common(task_id, request, db, require_feishu_sign=False)


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
    response_model=MediaExtractBasicContentResponse,
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
    log_extra = {"request_id": trace_key, "user_id": user_id, "app_id": app_id, "root_trace_key": root_trace_key,"platform":"s-site"}

    logger.info_to_db(
        f"不扣分提取接口接收媒体基础信息提取请求 (已解密): url={extract_request.url}",
        extra=log_extra
    )

    cleaned_url = await media_extract_content_helper.clean_url(extract_request.url)
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

        response_data = MediaExtractBasicContentResponse(
            code=200,
            message="成功提取媒体基础信息",
            # 确保 media_content 是字典或可以解包给 MediaContentResponse
            data=MediaBasicContentResponse(**media_content) if isinstance(media_content, dict) else media_content,
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





@router.post(
    "/sn",
    response_model=SearchNoteResponse,
    summary="按平台搜索笔记内容",
    description="根据平台和关键词搜索笔记内容，目前支持小红书（XHS）等。",
    tags=["媒体服务"]
)
@require_feishu_signature()
@require_auth_key()
async def search_note_by_kword(
    req: Request,
    s_req: SearchNoteRequest,
    db: AsyncSession = Depends(get_db)
):
    trace_key = request_ctx.get_trace_key()
    app_id = request_ctx.get_app_id()
    source = request_ctx.get_source()
    user_id = request_ctx.get_cappa_user_id()
    user_name = request_ctx.get_user_name()
    ip_address = req.client.host if req.client else "unknown_ip"
    root_trace_key = request_ctx.get_root_trace_key()
    platform = 'platform'

    request_context = RequestContext(
        trace_id=trace_key, app_id=app_id, user_id=user_id, source=None, user_name=None, ip=None, timestamp=datetime.now()
    )
    log_extra = {"request_id": trace_key, "user_id": user_id, "app_id": app_id, "platform": s_req.platform, "query": s_req.query}
    logger.info_to_db(f"收到平台笔记搜索请求: platform={s_req.platform}, query={s_req.query}, num={s_req.num}, sort={s_req.qsort}", extra=log_extra)
    try:
        result = await media_service.search_note_by_kword(trace_key,s_req.platform, s_req.query, s_req.num, s_req.qsort,log_extra)
        logger.info_to_db(f"平台笔记搜索成功: platform={s_req.platform}, query={s_req.query}, result_count={len(result) if result else 0}", extra=log_extra)
    
        points_consumed = 0;
        if not result:
            logger.warning(f"平台笔记搜索没找到结果: platform={s_req.platform}, query={s_req.query}, result_count=0", extra=log_extra)
            return SearchNoteResponse(
                code=200,
                message="没有对应搜索结果",
                data=SearchNoteData(),
            )

        
        points_consumed = settings.BASIC_CONSUME_POINT;
        request_ctx.set_consumed_points(points_consumed)

        note_data = SearchNoteData()
        note_data.memo = f'使用关键字【{s_req.query}】-搜索平台【{s_req.platform}】-得到【{len(result)}】条结果,消耗【{points_consumed}】积分'
        note_data.file_link = await media_service.extract_xiaohongshu_data_str(result)
        note_data.total_required = points_consumed

        return SearchNoteResponse(
            code=200,
            message="success",
            data=note_data,
            request_context=request_context
        )
    except Exception as e:
        logger.error(f"search_note_by_platform_api error: {e}", extra=log_extra)
        raise HTTPException(status_code=500, detail=str(e))




@router.post(
    "/kol",
    response_model=KOLResponse,
    summary="按平台搜索达人",
    description="根据平台和关键词搜索笔记内容，目前支持小红书（XHS）等。",
    tags=["媒体服务"]
)
# @TollgateConfig(title="搜索达人", type="media", base_tollgate="10", current_tollgate="1", plat="api")
# @require_feishu_signature()
# @require_auth_key()
async def search_kol_by_url(
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    trace_key = request_ctx.get_trace_key()
    app_id = request_ctx.get_app_id()
    source = request_ctx.get_source()
    user_id = request_ctx.get_cappa_user_id()
    user_name = request_ctx.get_user_name()
    ip_address = req.client.host if req.client else "unknown_ip"
    root_trace_key = request_ctx.get_root_trace_key()

    cq_data = await req.json()
    user_url = str(cq_data.get("url"))
    formatter = Media_extract_format()
    platform = formatter._identify_platform(user_url)

    request_context = RequestContext(
        trace_id=trace_key, app_id=app_id, user_id=user_id, source=None, user_name=None, ip=None, timestamp=datetime.now()
    )
    log_extra = {"request_id": trace_key, "user_id": user_id, "app_id": app_id, "platform": platform, "user_url": user_url}
    logger.info_to_db(f"按平台搜索达人-search_kol_by_url: platform={platform}, user_url={user_url}", extra=log_extra)

    try:
        result = await media_service.async_get_user_full_info( platform,user_url,log_extra )
        logger.info_to_db(f"按平台搜索达人-search_kol_by_url-成功: platform={platform}, user_url={user_url}, result_count={len(result) if result else 0}", extra=log_extra)
    
        points_consumed = 0;
        if not result:
            logger.warning(f"按平台搜索达人-async_get_user_full_info-没找到结果: platform={platform}, user_url={user_url}, result_count=0", extra=log_extra)
            return SearchNoteResponse(
                code=200,
                message="按平台搜索达人没有对应搜索结果",
                data=SearchNoteData(),
            )

        
        # points_consumed = settings.BASIC_CONSUME_POINT;
        # request_ctx.set_consumed_points(points_consumed)

        kol = result
        # note_data.memo = f'使用关键字【{s_req.query}】-搜索平台【platform}】-得到【{len(result)}】条结果,消耗【{points_consumed}】积分'
        # note_data.file_link = await media_service.extract_xiaohongshu_data_str(result)
        # note_data.total_required = points_consumed

        logger.info_to_db(f"按平台搜索达人-search_kol_by_url-返回结果: platform={platform}, user_url={user_url}, kol={kol}", extra=log_extra)

        return KOLResponse(
            code=200,
            message="success",
            data=kol,
            request_context=request_context
        )
    except Exception as e:
        logger.error(f"search_kol_by_url error: {e}", extra=log_extra)
        raise HTTPException(status_code=500, detail=str(e))

