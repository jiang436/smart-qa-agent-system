"""API 路由 — 按域拆分的子路由"""

from fastapi import APIRouter

from .approval import router as approval_router
from .auth import router as auth_router
from .chat import router as chat_router
from .knowledge import router as knowledge_router
from .orders import router as orders_router
from .search_logs import router as search_logs_router
from .session import router as session_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(session_router)
router.include_router(approval_router)
router.include_router(knowledge_router)
router.include_router(search_logs_router)
router.include_router(orders_router)
