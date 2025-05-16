import re
import os
import time

import json
import requests 
from requests.exceptions import RequestException # 导入 requests 的异常类
from typing import Dict, Any, Optional, Tuple, Union, List
from datetime import datetime

from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
import httpx

class KuaishouService:
    def __init__(self):
        pass
    def get_video_info(
        self, 
        task_id: str,
        url: str,
        log_extra: dict
    ) -> Optional[Dict[str, Any]]:
        logger.info(f"[{task_id}] 开始获取快手视频基础信息: {url}", extra=log_extra)

        kuaishou_site = settings.KUAISHOU_SITE
        kuaishou_api_endpoint = kuaishou_site + "/info"

        payload = {"url": url} # 请求体
        headers = {"Content-Type": "application/json"}
        logger.info(f"调用 Kuaishou API: {kuaishou_api_endpoint} for URL: {url}", extra=log_extra)

        try:
            # 发送 POST 请求到 API
            response = requests.post(kuaishou_api_endpoint, headers=headers, json=payload, timeout=30) # 设置超时
            response.raise_for_status() # 如果状态码不是 2xx，则抛出异常

            # 解析 JSON 响应
            api_response = response.json()
            if api_response.get("status") == "success" and api_response.get("data"):
                video_info = api_response["data"] # 提取 video_info 部分
                logger.info(f"task {task_id} -- Kuaishou API 调用成功，获取到信息。video_info is {video_info}", extra=log_extra)

                return video_info
            else:
                # API 返回成功但没有 video_info 或 status 不是 success
                logger.info(f"task {task_id} -- Kuaishou API 调用完成，但未能获取有效视频信息: {api_response.get('message')}", extra=log_extra)
        except RequestException as e:
            # 处理网络请求错误 (连接错误、超时等)
            logger.error(f"task {task_id} -- 调用 Kuaishou API 时发生网络错误: {e}", exc_info=True, extra=log_extra)
        except json.JSONDecodeError:
            # 处理 API 返回非 JSON 格式的情况
            logger.error(f"task {task_id} -- Kuaishou API 返回了无效的 JSON 响应: {response.text}", exc_info=True, extra=log_extra)
        except Exception as api_err:
            # 处理其他可能的错误
            logger.error(f"task {task_id} -- 调用 Kuaishou API 时发生未知错误: {api_err}", exc_info=True, extra=log_extra)

        

    async def async_get_video_info(
        self, task_id: str, url: str, log_extra: dict) -> Optional[Dict[str, Any]]:
        payload = {"url": url}
        headers = {"Content-Type": "application/json"}
        logger.info(f"[{task_id}] 开始获取快手视频基础信息: {url}", extra=log_extra)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                kuaishou_site = settings.KUAISHOU_SITE
                kuaishou_api_endpoint = kuaishou_site + "/info"

                response = await client.post(kuaishou_api_endpoint, headers=headers, json=payload)
                response.raise_for_status()
                api_response = response.json()
                if api_response.get("status") == "success" and api_response.get("data"):
                    video_info = api_response["data"]
                    logger.info(f"task {task_id} -- Kuaishou API 调用成功，获取到信息。video_info is {video_info}", extra=log_extra)
                    return video_info
                else:
                    logger.info(f"task {task_id} -- Kuaishou API 调用完成，但未能获取有效视频信息: {api_response.get('message')}", extra=log_extra)
        except httpx.RequestError as e:
            logger.error(f"task {task_id} -- 调用 Kuaishou API 时发生网络错误: {e}", exc_info=True, extra=log_extra)
        except Exception as api_err:
            logger.error(f"task {task_id} -- 调用 Kuaishou API 时发生未知错误: {api_err}", exc_info=True, extra=log_extra)
        return None