
from fastapi import FastAPI, Request
from fastapi.responses import Response
import logging

logger = logging.getLogger(__name__)

async def log_requests(request: Request, call_next):
    # 获取请求的基本信息
    request_body = await request.body()
    logger.info(f"请求: {request.method} {request.url}，Body: {request_body.decode('utf-8')}")

    # 处理请求，并捕获响应
    response = await call_next(request)

    # 由于响应流可能只能消费一次，所以需要将其完整读取后再重建 Response 对象
    response_body = b""
    async for chunk in response.body_iterator:
        response_body += chunk

    logger.info(f"响应: 状态码: {response.status_code}，Body: {response_body.decode('utf-8')}")

    # 重新创建 Response 对象
    return Response(content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type)