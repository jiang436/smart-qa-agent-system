"""知识库路由 — 文件上传 / 索引管理 / 状态查询

提供 REST API 接口管理 RAG 知识库:
  - POST /api/v1/knowledge/upload    上传单个文件（PDF/MD/TXT）
  - POST /api/v1/knowledge/reload    从 data/knowledge/ 重新加载全部
  - GET  /api/v1/knowledge/status    知识库状态统计
"""

import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from pymilvus import MilvusClient

from smart_qa.config import settings
from smart_qa.knowledge.document_parser import DocumentParser
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.observability.logger import logger
from smart_qa.rag.chunking import SmartDocumentSplitter

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _get_client() -> MilvusClient:
    """创建 MilvusClient 连接（MilvusClient 替代了弃用的 connections.connect）"""
    return MilvusClient(
        host=settings.milvus_host,
        port=settings.milvus_port,
    )


def _ensure_collection(client: MilvusClient) -> str:
    """确保集合存在（不存在则创建），返回集合名"""
    collection_name = settings.milvus_collection
    embedding = get_embedding()

    from pymilvus import MilvusClient, DataType

    if not client.has_collection(collection_name):
        schema = MilvusClient.create_schema(
            auto_id=True,
            enable_dynamic_field=False,
        )
        schema.add_field("id", datatype=DataType.INT64, is_primary=True)
        schema.add_field("vector", datatype=DataType.FLOAT_VECTOR, dim=embedding.dimension)
        schema.add_field("content", datatype=DataType.VARCHAR, max_length=4096)
        schema.add_field("source", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field("title", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field("category", datatype=DataType.VARCHAR, max_length=64)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            metric_type="COSINE",
            index_type="IVF_FLAT",
            params={"nlist": 128},
        )

        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info("Milvus 集合已创建: {} (dim={})", collection_name, embedding.dimension)
    else:
        client.load_collection(collection_name)

    return collection_name


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传单个文件到知识库（PDF / MD / TXT）"""
    if not DocumentParser.is_supported(file.filename or ""):
        raise HTTPException(400, detail="不支持的文件类型，仅支持: .pdf / .md / .txt")

    content_bytes = await file.read()
    ext = os.path.splitext(file.filename or "upload")[1].lower()

    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.write(content_bytes)
    tmp.close()

    try:
        parser = DocumentParser()
        text = parser.extract_text(tmp.name)
        if not text.strip():
            raise HTTPException(400, detail="无法从文件中提取文字内容")

        splitter = SmartDocumentSplitter()
        doc_type = SmartDocumentSplitter.detect_type(tmp.name, text)
        chunks = splitter.split(
            text,
            doc_type=doc_type,
            metadata={
                "source": file.filename or "",
                "title": os.path.splitext(file.filename or "upload")[0],
                "category": "upload",
            },
        )
        if not chunks:
            raise HTTPException(400, detail="文件分段后无有效内容")

        embedding = get_embedding()
        client = _get_client()
        collection_name = _ensure_collection(client)

        texts = [c["content"] for c in chunks]
        vectors = embedding.encode(texts)

        data = [
            {
                "vector": vectors[i].tolist(),
                "content": chunks[i]["content"][:4096],
                "source": chunks[i]["source"][:256],
                "title": chunks[i]["title"][:256],
                "category": chunks[i].get("category", "upload")[:64],
            }
            for i in range(len(chunks))
        ]
        client.insert(collection_name, data)
        client.flush(collection_name)

        logger.info("知识库上传: file={} chunks={}", file.filename, len(chunks))
        return {
            "status": "ok",
            "file": file.filename,
            "chunks": len(chunks),
            "dimension": embedding.dimension,
        }
    finally:
        os.unlink(tmp.name)


@router.post("/reload")
async def reload_knowledge():
    """从 data/knowledge/ 重新加载所有知识文档"""
    from smart_qa.scripts.init_vector_store import init_vector_store

    client = _get_client()
    if client.has_collection(settings.milvus_collection):
        client.drop_collection(settings.milvus_collection)
        logger.info("已删除旧集合: {}", settings.milvus_collection)

    init_vector_store()
    return {"status": "ok", "message": "知识库已重新加载"}


@router.get("/status")
async def knowledge_status():
    """查询知识库状态"""
    try:
        client = _get_client()
        collection_name = settings.milvus_collection

        if not client.has_collection(collection_name):
            return {"status": "empty", "message": "知识库为空，请先上传文档"}

        client.load_collection(collection_name)
        stats = client.get_collection_stats(collection_name)
        dim = get_embedding().dimension

        return {
            "status": "ok",
            "collection": collection_name,
            "total_documents": stats.get("row_count", 0),
            "dimension": dim,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
