"""向后兼容入口 — 代理到 src.app.web"""
from src.app.web import app, lifespan

__all__ = ["app", "lifespan"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app.web:app", host="0.0.0.0", port=8000, reload=True)
