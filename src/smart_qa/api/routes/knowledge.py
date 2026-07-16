"""知识库路由 — 文件上传 / 索引管理 / 状态查询

提供 REST API 接口管理 RAG 知识库:
  - POST /api/v1/knowledge/upload    上传单个文件（PDF/MD/TXT）
  - POST /api/v1/knowledge/reload    从 data/knowledge/ 重新加载全部
  - GET  /api/v1/knowledge/status    知识库状态统计 + 上传记录
  - GET  /api/v1/knowledge/files     已上传文件列表

上传记录存储在 PostgreSQL 中，重启后不丢失。
"""

import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pymilvus import MilvusClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_qa.config import settings
from smart_qa.database.engine import get_db
from smart_qa.knowledge.document_parser import DocumentParser
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.models.knowledge_file import KnowledgeFile
from smart_qa.observability.logger import logger
from smart_qa.rag.chunking import SmartDocumentSplitter

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _get_milvus() -> MilvusClient:
    return MilvusClient(host=settings.milvus_host, port=settings.milvus_port, timeout=5)


def _ensure_collection(client: MilvusClient) -> str:
    collection_name = settings.milvus_collection
    embedding = get_embedding()
    from pymilvus import DataType

    if not client.has_collection(collection_name):
        schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("id", datatype=DataType.INT64, is_primary=True)
        schema.add_field("vector", datatype=DataType.FLOAT_VECTOR, dim=embedding.dimension)
        schema.add_field("content", datatype=DataType.VARCHAR, max_length=4096)
        schema.add_field("source", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field("title", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field("category", datatype=DataType.VARCHAR, max_length=64)
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="vector", metric_type="COSINE", index_type="IVF_FLAT", params={"nlist": 128})
        client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)
        logger.info("Milvus 集合已创建: {} (dim={})", collection_name, embedding.dimension)
    else:
        client.load_collection(collection_name)
    return collection_name


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not DocumentParser.is_supported(file.filename or ""):
        raise HTTPException(400, detail="不支持的文件类型，仅支持: .pdf / .md / .txt")

    # 文件大小校验（上限 10MB）
    MAX_FILE_SIZE = 10 * 1024 * 1024
    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(400, detail=f"文件过大，上限 10MB，当前 {len(content_bytes) / 1024 / 1024:.1f}MB")

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
        client = _get_milvus()
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

        # 记录上传到 PostgreSQL
        import os as _os

        record = KnowledgeFile(
            filename=file.filename or "unknown",
            file_type=_os.path.splitext(file.filename or "unknown")[1].lower().lstrip(".") or "unknown",
            chunks=len(chunks),
            dimension=embedding.dimension,
            uploaded_at=datetime.utcnow(),
        )
        db.add(record)
        await db.commit()

        logger.info("知识库上传: file={} chunks={}", file.filename, len(chunks))

        # 增量更新 BM25 索引
        try:
            from smart_qa.rag.retrieval import _shared_bm25

            if _shared_bm25 and _shared_bm25.is_built:
                bm25_texts = [c["content"] for c in chunks if len(c["content"]) > 20]
                if bm25_texts:
                    _shared_bm25.add_documents(bm25_texts)
                    _shared_bm25.save()
        except Exception as e:
            logger.warning("BM25 增量更新失败: {}", e)

        return {"status": "ok", "file": file.filename, "chunks": len(chunks), "dimension": embedding.dimension}
    finally:
        os.unlink(tmp.name)


@router.post("/reload")
async def reload_knowledge(db: AsyncSession = Depends(get_db)):
    from smart_qa.scripts.init_vector_store import init_vector_store

    client = _get_milvus()
    if client.has_collection(settings.milvus_collection):
        client.drop_collection(settings.milvus_collection)
        logger.info("已删除旧集合: {}", settings.milvus_collection)

    init_vector_store()

    # 重建后清空上传记录
    from sqlalchemy import delete as sa_delete

    await db.execute(sa_delete(KnowledgeFile))
    await db.commit()
    return {"status": "ok", "message": "知识库已重新加载"}


@router.get("/status")
async def knowledge_status(db: AsyncSession = Depends(get_db)):
    try:
        client = _get_milvus()
        collection_name = settings.milvus_collection
        if not client.has_collection(collection_name):
            return {
                "status": "empty",
                "collection": collection_name,
                "total_documents": 0,
                "dimension": 0,
                "uploaded_files": [],
            }

        client.load_collection(collection_name)
        stats = client.get_collection_stats(collection_name)
        dim = get_embedding().dimension

        # 从 PG 读上传记录
        result = await db.execute(select(KnowledgeFile).order_by(KnowledgeFile.uploaded_at.desc()))
        files = [
            {
                "filename": r.filename,
                "file_type": r.file_type,
                "chunks": r.chunks,
                "dimension": r.dimension,
                "uploaded_at": r.uploaded_at.isoformat(),
            }
            for r in result.scalars().all()
        ]

        return {
            "status": "ok",
            "collection": collection_name,
            "total_documents": stats.get("row_count", 0),
            "dimension": dim,
            "uploaded_files": files,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/files")
async def list_uploaded_files(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(KnowledgeFile).order_by(KnowledgeFile.uploaded_at.desc()))
    files = [
        {
            "filename": r.filename,
            "file_type": r.file_type,
            "chunks": r.chunks,
            "dimension": r.dimension,
            "uploaded_at": r.uploaded_at.isoformat(),
        }
        for r in result.scalars().all()
    ]
    return {"files": files}


# ── BM25 ──


@router.get("/bm25/status")
async def bm25_status():
    """BM25 索引状态"""
    from smart_qa.rag.retrieval import _shared_bm25

    bm25 = _shared_bm25
    if not bm25 or not bm25.is_built:
        return {"status": "empty", "doc_count": 0, "built_at": "", "terms": 0}

    return {
        "status": "ok",
        "doc_count": bm25.doc_count,
        "built_at": bm25.built_at_str,
        "terms": len(bm25.inverted_index),
    }


@router.post("/bm25/rebuild")
async def bm25_rebuild():
    """重建 BM25 索引并持久化 — 和 Milvus 使用完全相同的数据源"""
    from smart_qa.knowledge.bm25 import BM25Index
    from smart_qa.rag.retrieval import collect_knowledge_texts, set_shared_bm25

    docs = collect_knowledge_texts()

    bm25 = BM25Index()
    bm25.build(docs)
    bm25.save()

    set_shared_bm25(bm25)

    return {
        "status": "ok",
        "doc_count": bm25.doc_count,
        "built_at": bm25.built_at_str,
        "terms": len(bm25.inverted_index),
    }
