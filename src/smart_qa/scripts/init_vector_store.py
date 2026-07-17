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
from smart_qa.knowledge.vector_store import get_embedding
from smart_qa.rag.chunking import SmartDocumentSplitter

# ═══════════════════════════════════════════
# 文档读取
# ═══════════════════════════════════════════


def read_documents(docs_dir: str) -> list[dict]:
    """用 DirectoryLoader 批量加载 + SmartDocumentSplitter 切分

    自动识别 PDF/MD/TXT，按语义元素切分后输出 chunk 列表。
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
                elements = parser.load(filepath)  # list[Document]
            except Exception as e:
                print(f"[InitVector] 读取失败: {filepath}: {e}")
                continue

            if not elements:
                continue

            # 从第一个标题提取文档标题
            title = filename.rsplit(".", 1)[0]
            for el in elements:
                if el.metadata.get("element_type") in ("Title", "Header") and el.page_content:
                    t = el.page_content.lstrip("#").strip()
                    if t:
                        title = t
                        break

            # 拼接所有元素 → 完整 Markdown
            full_text = "\n\n".join(el.page_content for el in elements if el.page_content.strip())
            if not full_text.strip():
                continue

            doc_type = SmartDocumentSplitter.detect_type(filename, full_text)
            chunks = splitter.split(
                full_text, doc_type=doc_type,
                metadata={"source": filename, "title": title, "category": category},
            )
            for chunk in chunks:
                chunk["element_types"] = _collect_element_types(elements)
                documents.append(chunk)
            print(f"[InitVector] {filename} → {len(chunks)} chunks ({len(elements)} elements)")

    print(f"[InitVector] 已读取 {len(documents)} 个文档片段 (来自 {docs_dir})")
    return documents


def _collect_element_types(elements) -> list[str]:
    return list(dict.fromkeys(el.metadata.get("element_type", "?") for el in elements))


# ═══════════════════════════════════════════
# Milvus 操作（MilvusClient 新 API）
# ═══════════════════════════════════════════


def ensure_collection(client: MilvusClient, collection_name: str, dim: int) -> str:
    """确保集合存在，不存在则创建"""
    if client.has_collection(collection_name):
        client.load_collection(collection_name)
        print(f"[InitVector] 集合已存在: {collection_name} (dim={dim})")
        return collection_name

    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("id", datatype=DataType.INT64, is_primary=True)
    schema.add_field("vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("content", datatype=DataType.VARCHAR, max_length=4096)
    schema.add_field("source", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field("title", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field("category", datatype=DataType.VARCHAR, max_length=64)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        metric_type="COSINE",
        index_type="HNSW",
        params={"M": 16, "efConstruction": 256},
    )

    client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)
    print(f"[InitVector] 集合已创建: {collection_name} (dim={dim})")
    return collection_name


def _enrich_content(chunk: dict) -> str:
    """将 header/section 元数据拼入 content，确保标题信息参与 Embedding

    否则 "### 米家全能扫拖机器人 M40 S" 只存为元数据，
    "基站功能：自动洗拖布" 里没有型号名，检索时对不上。
    """
    content = chunk.get("content", "")
    section = chunk.get("section", "")
    header = chunk.get("header", "")

    # 如果 content 已包含 header，不重复拼接
    prefix_parts = []
    if section and section not in content:
        prefix_parts.append(section)
    if header and header not in content:
        prefix_parts.append(header)

    if prefix_parts:
        prefix = " > ".join(prefix_parts)
        return f"{prefix}\n{content}"
    return content


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
        texts = [_enrich_content(c) for c in batch]
        vectors = embedding_model.encode(texts)

        data = [
            {
                "vector": vectors[idx].tolist(),
                "content": texts[idx][:4096],
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
    # reload 使新插入数据立即可查
    client.release_collection(collection_name)
    client.load_collection(collection_name)
    print(f"[InitVector] 插入完成: {inserted}/{total} 条")


# ── 没有文档时的默认知识内容 ──

DEFAULT_KNOWLEDGE = {
    "consumables": """# 耗材维护指南

## 常见耗材类型
- 边刷：负责沿墙和角落清扫，刷毛磨损后清扫效果下降
- 主刷/滚刷：负责地面主清扫，缠绕毛发需定期清理
- HEPA滤网：过滤排出空气，到期后影响吸力和空气质量
- 拖布：接触地面拖洗，随使用次数增加性能衰减
- 集尘袋：收集灰尘垃圾，装满后需更换

## 更换周期建议
- 边刷: 3-6个月（刷毛缩短1/3以上时更换）
- 主刷: 6-12个月（刷毛脱落或橡胶条磨损时更换）
- HEPA滤网: 3-4个月（不透光或颜色变深时更换）
- 拖布: 2-3个月（变硬、发黄或洗不干净时更换）
- 集尘袋: 60-90天（装满或吸力下降时更换）

## 选购建议
- 边刷/拖布：第三方品牌性价比高，够用
- 滤网/滚刷：建议原厂，对清洁效果影响大
- 清洁液：必须原厂，第三方可能腐蚀水箱管路
- 不要使用84消毒液或酒精
""",
    "fault_troubleshooting": """# 故障排查指南

## 常见错误码

### E01 - 跌落传感器异常
- 原因: 扫地机检测到悬空状态
- 解决: 将扫地机放回充电座附近平整地面，重新启动

### E02 - 轮子卡住
- 原因: 驱动轮被异物缠绕或地毯卡住
- 解决: 检查轮子是否被线缆/头发缠绕，清理异物后重启

### E03 - 边刷不转
- 原因: 边刷卡住或电机故障
- 解决: 用干净布清理边刷轴，检查是否缠绕头发

### E04 - 尘盒未安装
- 原因: 尘盒未正确安装到位
- 解决: 确认尘盒完全推入，听到咔哒声

### E05 - 电池过热
- 原因: 电池温度过高保护
- 解决: 将设备移至阴凉处，待冷却后重新启动

### E06 - 激光雷达异常
- 原因: 激光雷达无法旋转或遮挡
- 解决: 检查激光雷达是否有异物遮挡，清洁雷达表面

### E07 - Wi-Fi 连接失败
- 原因: 无法连接Wi-Fi网络
- 解决: 检查路由器信号强度，重新配网

### E08 - 水箱未安装
- 原因: 拖地模式下水箱未安装
- 解决: 安装水箱支架后再使用拖地功能

## 常见问题排查

### 扫地机不工作
1. 检查电量是否充足（>15%）
2. 检查是否在充电座范围内
3. 尝试重启设备（长按开机键10秒）

### 清扫不干净
1. 检查边刷/主刷磨损情况
2. 检查尘盒是否已满
3. 确认吸力模式（安静/标准/强力）

### 无法回充
1. 充电座指示灯是否亮
2. 充电座周围是否有障碍物
3. 尝试手动对齐充电触点

### 噪音过大
1. 检查主刷/边刷是否有异物缠绕
2. 检查滚轮是否卡住
3. 确认是否在强力模式下运行

### 地图丢失
1. 检查是否在重新建图模式
2. 确认激光雷达无遮挡
3. 检查App版本和固件是否最新
""",
    "user_manual": """# 产品使用手册

## 快速开始
1. 将充电座靠墙放置，两侧留出0.5米空间
2. 安装边刷（对准卡槽按下）
3. 长按开机键3秒启动设备
4. 下载App并注册账号
5. 按App提示完成Wi-Fi配网

## 定时清扫设置
1. 打开App → 设备 → 定时清扫
2. 点击添加定时任务
3. 选择时间、清扫模式、清扫区域

## 清扫模式
- 安静模式: 低噪音，适合夜间
- 标准模式: 平衡清洁力和噪音
- 强力模式: 最大吸力
- 拖地模式: 需要安装水箱和拖布

## 维护保养
- 每次清扫后清空尘盒
- 每周清洁传感器和充电触点
- 每月清洗滤网
- 每3个月更换边刷
- 每6个月检查主刷磨损

## 支持功能
- 支持多层地图（最多3张）
- 支持虚拟墙和禁区
- 支持断点续扫
- 支持悬崖传感器
""",
}


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
    client = MilvusClient(host=settings.milvus_host, port=settings.milvus_port)

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
