"""运维脚本"""

try:
    from .init_vector_store import init_vector_store
except ImportError:
    init_vector_store = None  # pymilvus not installed
