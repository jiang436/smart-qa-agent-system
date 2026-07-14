"""API 依赖注入 — FastAPI Depends() 集中管理

所有路由通过 Depends() 获取所需的安全检查组件，避免硬编码实例化。

提供的依赖:
  - check_rate_limit:   检查请求是否超出三层令牌桶限流 (429)
  - check_security:     检查输入是否包含敏感词/注入内容 (400)
  - get_agent_graph:    获取 LangGraph 编译后的图（同 smart_qa.deps）

请求处理管线:
    POST 请求进入路由前依次经过:
        check_rate_limit(user_id 维度的令牌桶检查)
        → check_security(message 的四层安全过滤)
        → 路由处理 → 响应

    GET 请求跳过安全检查（限流和安全过滤均不生效）。

用法:
    @router.post("/chat")
    async def chat(
        req: ChatRequest,
        _: None = Depends(check_rate_limit),
        _: None = Depends(check_security),
    ):
        ...
"""

from fastapi import Depends, HTTPException, Request

from smart_qa.deps import get_rate_limiter, get_security
from smart_qa.security import RateLimiter, SensitiveFilter


async def check_rate_limit(
    request: Request,
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    """检查请求频率限制

    从请求体中提取 user_id，调用 RateLimiter.check_request() 进行三层检查：
      1. 全局令牌桶：所有用户共享
      2. 用户级令牌桶：每个用户独立
      3. 每日 Token 预算（通过 deduct_token 方法）

    Args:
        request: FastAPI 请求对象（GET 请求跳过限流检查）
        limiter: RateLimiter 单例（由 Depends 注入）

    Raises:
        HTTPException 429: 请求频率超过限制

    设计说明:
        GET 请求（如健康检查、页面加载）跳过限流。
        限流基于 user_id，从 JSON body 提取，提取失败则视为 anonymous。
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

    对 POST 请求的消息内容执行四道安全防线：
      1. AC 自动机敏感词匹配（暴力、色情、赌博等）
      2. Prompt 注入检测（忽略指令、DAN角色扮演等）
      3. 代码注入检测（XSS标签、SQL注入、Shell命令等）
      4. PII 输出过滤（在响应层通过 check_output 执行）

    Args:
        request: FastAPI 请求对象（GET 请求跳过安全检查）
        security: SensitiveFilter 单例（由 Depends 注入）

    Raises:
        HTTPException 400: 输入内容被安全策略拦截

    设计说明:
        拦截是在输入层做的，输出层的 PII 过滤在路由中独立调用 security.check_output()。
        两者职责分离：输入层防御攻击，输出层保护隐私。
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
