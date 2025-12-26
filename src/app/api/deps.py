"""API 依赖注入 — FastAPI Depends() 集中管理

所有路由通过 Depends() 获取所需组件，避免硬编码实例化。

提供的依赖:
  - check_rate_limit:   检查请求是否超出限流
  - check_security:     检查输入是否包含敏感/注入内容
  - get_agent_graph:    获取 LangGraph 编译后的图

Usage:
    @router.post("/chat")
    async def chat(
        req: ChatRequest,
        _: None = Depends(check_rate_limit),
        _: None = Depends(check_security),
    ):
        ...
"""

from fastapi import Depends, HTTPException, Request

from src.app.deps import get_rate_limiter, get_security
from src.security import RateLimiter, SensitiveFilter


async def check_rate_limit(
    request: Request,
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    """检查请求频率限制

    从请求体中提取 user_id（仅对 POST 请求）。
    对于 GET 请求，跳过限流检查。
    """
    if request.method == "GET":
        return

    # 尝试从请求体获取 user_id
    user_id = "anonymous"
    try:
        body = await request.json()
        user_id = body.get("user_id", "anonymous")
    except Exception:
        pass

    if not limiter.check_request(user_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


async def check_security(
    request: Request,
    security: SensitiveFilter = Depends(get_security),
) -> None:
    """检查输入内容安全性

    对 POST /chat 类请求检查消息内容。
    """
    if request.method == "GET":
        return

    try:
        body = await request.json()
        message = body.get("message", "")
        if message:
            result = security.check_input(message)
            if not result["allowed"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"请求被安全策略拦截: {result['blocked_reason']}",
                )
    except HTTPException:
        raise
    except Exception:
        pass
