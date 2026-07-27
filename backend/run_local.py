"""
Local development runner - uses SQLite (no Docker required).

Run with: python run_local.py
Access at: http://localhost:8000
API docs: http://localhost:8000/docs
"""

import os

# MUST set env vars BEFORE any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./dev.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["NAMECOM_USERNAME"] = os.environ.get("NAMECOM_USERNAME", "yeychanthy168169@gmail.com")
os.environ["NAMECOM_API_TOKEN"] = os.environ.get("NAMECOM_API_TOKEN", "b4ab6ca90ca353459062840a6a9a8e77d3dbcdd0")
os.environ["SECRET_KEY"] = "dev-secret-key-not-for-production"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "@zy_sal90"

if __name__ == "__main__":
    # Clear the lru_cache to pick up new env vars
    from app.core.config import get_settings
    get_settings.cache_clear()

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
