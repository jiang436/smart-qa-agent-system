"""初始化向量库 — 将知识文档导入 Milvus

读取 data/knowledge/ 目录下的文档，
分段 → 嵌入 → 存入 Milvus 向量集合。

Usage:
    uv run python -m smart_qa.scripts.init_vector_store

    或代码调用:
    from smart_qa.scripts.init_vector_store import init_vector_store
    init_vector_store()
"""

import os

from pymilvus import DataType, MilvusClient

from smart_qa.config import settings
from smart_qa.knowledge.default_data import DEFAULT_KNOWLEDGE
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.rag.chunking import SmartDocumentSplitter

# ═══════════════════════════════════════════
# 文档读取
# ═══════════════════════════════════════════


def read_documents(docs_dir: str) -> list[dict]:
    """递归读取 docs_dir 下所有支持的文档（md/txt/pdf）

    Returns:
        [{"content": "...", "source": "...", "title": "...", "category": "...", ...}]
    """
    from smart_qa.knowledge.document_parser import DocumentParser
    from smart_qa.rag.chunking import SmartDocumentSplitter

    parser = DocumentParser()
    splitter = SmartDocumentSplitter()
    documents = []

    if not os.path.isdir(docs_dir):
        print(f"[InitVector] 知识目录不存在: {docs_dir}")
        return documents

    for root, _dirs, files in os.walk(docs_dir):
        for filename in files:
            filepath = os.path.join(root, filename)
            if not DocumentParser.is_supported(filepath):
                continue

            rel_path = os.path.relpath(filepath, docs_dir)
            category = rel_path.split(os.sep)[0]

            try:
                content = parser.extract_text(filepath)
            except Exception as e:
                print(f"[InitVector] 读取失败: {filepath}: {e}")
                continue

            if not content.strip():
                continue

            title = filename.rsplit(".", 1)[0]
            for line in content.split("\n")[:5]:
                line = line.strip()
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            doc_type = SmartDocumentSplitter.detect_type(filename, content)
            chunks = splitter.split(
                content,
                doc_type=doc_type,
                metadata={
                    "source": rel_path,
                    "title": title,
                    "category": category,
                },
            )
            for chunk in chunks:
                documents.append(chunk)
            print(f"[InitVector] {filename} → {len(chunks)} chunks (type={doc_type})")

    print(f"[InitVector] 已读取 {len(documents)} 个文档片段 (来自 {docs_dir})")
    return documents


# ═══════════════════════════════════════════
# Milvus 操作（MilvusClient 新 API）
# ═══════════════════════════════════════════


def ensure_collection(client: MilvusClient, collection_name: str, dim: int) -> str:
    """确保集合存在且维度匹配，不匹配则重建"""
    if client.has_collection(collection_name):
        # 检查现有集合维度
        try:
            info = client.describe_collection(collection_name)
            existing_dim = info.get("dim") or next(
                (f.get("params", {}).get("dim") for f in info.get("fields", []) if f.get("name") == "vector"), 0
            )
            if existing_dim == dim:
                client.load_collection(collection_name)
                print(f"[InitVector] 集合已存在: {collection_name} (dim={dim})")
                return collection_name
            else:
                print(f"[InitVector] 维度不匹配 (现有={existing_dim}, 新={dim})，删除重建")
                client.drop_collection(collection_name)
        except Exception as e:
            print(f"[InitVector] 检查集合失败: {e}，删除重建")
            try:
                client.drop_collection(collection_name)
            except Exception:
                pass

    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("id", datatype=DataType.INT64, is_primary=True)
    schema.add_field("vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("content", datatype=DataType.VARCHAR, max_length=4096)
    schema.add_field("source", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field("title", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field("category", datatype=DataType.VARCHAR, max_length=64)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", metric_type="COSINE", index_type="IVF_FLAT", params={"nlist": 128})

    client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)
    print(f"[InitVector] 集合已创建: {collection_name} (dim={dim})")
    return collection_name


def insert_to_milvus(
    client: MilvusClient, collection_name: str, chunks: list[dict], embedding_model, batch_size: int = 50
):
    """批量将 chunk 写入 Milvus

    Args:
        client: MilvusClient 实例
        collection_name: 集合名
        chunks: 文档 chunk 列表（须含 content / source / title / category）
        embedding_model: EmbeddingModel 实例
        batch_size: 批量插入大小
    """
    total = len(chunks)
    inserted = 0

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["content"] for c in batch]
        vectors = embedding_model.encode(texts)

        data = [
            {
                "vector": vectors[idx].tolist(),
                "content": batch[idx]["content"][:4096],
                "source": batch[idx]["source"][:256],
                "title": batch[idx]["title"][:256],
                "category": batch[idx].get("category", "general")[:64],
            }
            for idx in range(len(batch))
        ]
        try:
            client.insert(collection_name, data)
            inserted += len(batch)
            print(f"  [{inserted}/{total}] 已插入...")
        except Exception as e:
            print(f"  [ERROR] 批量插入失败: {e}")

    client.flush(collection_name)
    print(f"[InitVector] 插入完成: {inserted}/{total} 条")


# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════


def init_vector_store(docs_dir: str = None, drop_existing: bool = False):
    """初始化向量库 — 完整流程

    Args:
        docs_dir: 知识文档目录路径，默认 data/knowledge/
        drop_existing: 是否删除已有集合重建
    """
    collection_name = settings.milvus_collection

    # 1. 创建 MilvusClient（新 API，无弃用警告）
    print(f"[InitVector] 连接 Milvus: {settings.milvus_host}:{settings.milvus_port}")
    client = MilvusClient(host=settings.milvus_host, port=settings.milvus_port, timeout=5)

    # 2. 删旧建新
    if drop_existing and client.has_collection(collection_name):
        client.drop_collection(collection_name)
        print(f"[InitVector] 已删除旧集合: {collection_name}")

    # 3. 获取 embedding 模型
    embedding = get_embedding()

    # 4. 创建或获取集合
    ensure_collection(client, collection_name, dim=embedding.dimension)

    # 5. 读取文档
    docs_dir = docs_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data", "knowledge"
    )
    documents = read_documents(docs_dir)

    # 6. 默认知识
    if not documents:
        print("[InitVector] 知识目录为空，使用内置默认知识")
        splitter = SmartDocumentSplitter(chunk_size=500, chunk_overlap=50, embedding_model=embedding)
        documents = []
        for category, content in DEFAULT_KNOWLEDGE.items():
            doc_type = splitter.detect_type(f"builtin/{category}.md", content)
            chunks = splitter.split(
                content,
                doc_type,
                {
                    "source": f"builtin/{category}.md",
                    "title": category,
                    "category": category,
                },
            )
            documents.extend(chunks)

    # 7. 插入 Milvus
    if documents:
        insert_to_milvus(client, collection_name, documents, embedding)
    else:
        print("[InitVector] 没有文档可插入")

    # 8. 状态
    stats = client.get_collection_stats(collection_name)
    print(f"[InitVector] 集合当前条目数: {stats.get('row_count', 0)}")
    print("[InitVector] 全部完成")


if __name__ == "__main__":
    init_vector_store()
