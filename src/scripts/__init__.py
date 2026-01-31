"""运维脚本"""

from .init_db import init_db, seed_data

try:
    from .init_vector_store import init_vector_store
except ImportError:
    init_vector_store = None  # pymilvus not installed
