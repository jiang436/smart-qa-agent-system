"""初始化向量库 — 将知识文档导入 Milvus

读取 data/knowledge/ 目录下的 .md 和 .txt 文档，
分段 → 嵌入 → 存入 Milvus 向量集合。

Usage:
    python -m app.scripts.init_vector_store

    或代码调用:
    from src.scripts.init_vector_store import init_vector_store
    init_vector_store()
"""

import os

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from src.app.config import settings
from src.knowledge.vector_store import get_embedding
from src.rag.chunking import SmartDocumentSplitter

# ── 文档分段 ──


def read_documents(docs_dir: str) -> list[dict[str, str]]:
    """递归读取 docs_dir 下所有 .md / .txt 文件

    Args:
        docs_dir: 知识文档根目录

    Returns:
        [{"content": "文本段落", "source": "相对路径", "title": "文档标题"}, ...]
    """
    documents = []

    if not os.path.isdir(docs_dir):
        print(f"[InitVector] 知识目录不存在: {docs_dir}")
        return documents

    for root, dirs, files in os.walk(docs_dir):
        for filename in files:
            if not filename.endswith((".md", ".txt", ".MD", ".TXT")):
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, docs_dir)
            category = rel_path.split(os.sep)[0]  # consumables / fault_troubleshooting / user_manual

            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"[InitVector] 读取失败: {filepath}: {e}")
                continue

            if not content.strip():
                continue

            # 提取标题（第一个 # 行或文件名）
            title = filename.rsplit(".", 1)[0]
            for line in content.split("\n")[:5]:
                line = line.strip()
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            # 分段：按双换行符拆分
            paragraphs = content.split("\n\n")
            for i, para in enumerate(paragraphs):
                para = para.strip()
                if len(para) < 10:  # 跳过过短的段落
                    continue

                documents.append(
                    {
                        "content": para,
                        "source": rel_path,
                        "title": title,
                        "category": category,
                        "chunk_index": i,
                    }
                )

    print(f"[InitVector] 已读取 {len(documents)} 个文档片段 (来自 {docs_dir})")
    return documents


def chunk_documents(documents: list[dict], max_chunk_size: int = 512) -> list[dict]:
    """将长段落进一步切分为更小的 chunk

    Args:
        documents: read_documents() 的输出
        max_chunk_size: 每 chunk 最大字符数

    Returns:
        切分后的文档列表
    """
    chunks = []

    for doc in documents:
        content = doc["content"]
        if len(content) <= max_chunk_size:
            chunks.append(doc)
        else:
            # 按句子边界切分
            sentences = content.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n")
            current_chunk = ""
            chunk_idx = 0

            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue

                if len(current_chunk) + len(sent) > max_chunk_size and current_chunk:
                    chunks.append(
                        {
                            **doc,
                            "content": current_chunk.strip(),
                            "chunk_index": f"{doc['chunk_index']}_{chunk_idx}",
                        }
                    )
                    current_chunk = sent
                    chunk_idx += 1
                else:
                    current_chunk += sent

            if current_chunk.strip():
                chunks.append(
                    {
                        **doc,
                        "content": current_chunk.strip(),
                        "chunk_index": f"{doc['chunk_index']}_{chunk_idx}",
                    }
                )

    print(f"[InitVector] 切分为 {len(chunks)} 个 chunk (max_size={max_chunk_size})")
    return chunks


# ── Milvus 操作 ──


def create_collection(collection_name: str, dim: int = 512):
    """创建 Milvus 集合（如果不存在）

    Schema:
      - id: int64 (auto_id)
      - vector: float_vector(512)
      - content: varchar(4096)
      - source: varchar(256)
      - title: varchar(256)
      - category: varchar(64)
    """
    if utility.has_collection(collection_name):
        print(f"[InitVector] 集合已存在: {collection_name}")
        return Collection(collection_name)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
    ]

    schema = CollectionSchema(fields, description="知识库向量集合")
    collection = Collection(collection_name, schema)

    # 创建索引（内积 IP 度量）
    index_params = {
        "metric_type": "IP",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    collection.create_index("vector", index_params)
    print(f"[InitVector] 集合已创建并建立索引: {collection_name}")
    return collection


def insert_to_milvus(collection, chunks: list[dict], embedding_model, batch_size: int = 50):
    """批量将 chunk 写入 Milvus

    Args:
        collection: Milvus Collection 对象
        chunks: 文档 chunk 列表
        embedding_model: EmbeddingModel 实例
        batch_size: 批量插入大小
    """
    total = len(chunks)
    inserted = 0

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]

        # 批量编码
        texts = [c["content"] for c in batch]
        vectors = embedding_model.encode(texts)

        # 准备插入数据
        data = [
            vectors.tolist(),
            [c["content"][:4096] for c in batch],
            [c["source"][:256] for c in batch],
            [c["title"][:256] for c in batch],
            [c["category"][:64] for c in batch],
        ]

        try:
            collection.insert(data)
            inserted += len(batch)
            print(f"  [{inserted}/{total}] 已插入...")
        except Exception as e:
            print(f"  [ERROR] 批量插入失败: {e}")

    collection.flush()
    print(f"[InitVector] 插入完成: {inserted}/{total} 条")


# ── 没有文档时的默认知识内容 ──

DEFAULT_KNOWLEDGE = {
    "consumables": """# 耗材兼容性指南

## X30 Pro 耗材兼容表
- 边刷: X30-SB-01 (原装), X30-SB-C (第三方兼容)
- 主刷: X30-MB-01 (原装), 通用型-T (第三方)
- HEPA滤网: X30-HF-01 (原装)
- 拖布: X30-MP-01 (原装), 通用拖布-M (第三方)
- 尘盒: X30-DB-01 (内置, 无需更换)

## 更换周期建议
- 边刷: 3-6个月 (根据使用频率)
- 主刷: 6-12个月
- HEPA滤网: 3-4个月
- 拖布: 2-3个月
- 建议定期检查磨损情况

## T10 耗材兼容表
- 边刷: T10-SB-01 (原装)
- 主刷: T10-MB-01 (原装)
- 滤网: T10-FL-01 (原装)

## X20 Pro 耗材兼容表
- 边刷: X20-SB-01 (原装), X20-SB-C (第三方)
- 主刷: X20-MB-01 (原装)
- 拖布: X20-MP-01 (原装)
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
- 解决: 将设备移至阴凉处，待冷却后重新启动。检查充电触点是否干净

### E06 - 激光雷达异常
- 原因: 激光雷达无法旋转或遮挡
- 解决: 检查激光雷达是否有异物遮挡，清洁雷达表面

### E07 - Wi-Fi 连接失败
- 原因: 无法连接Wi-Fi网络
- 解决: 检查路由器信号强度，重新配网（长按Wi-Fi键5秒）

### E08 - 水箱未安装
- 原因: 拖地模式下水箱未安装
- 解决: 安装水箱支架后再使用拖地功能

## 常见问题排查

### 扫地机不工作
1. 检查电量是否充足（>15%）
2. 检查是否在充电座范围内
3. 检查App是否在线
4. 尝试重启设备（长按开机键10秒）

### 清扫不干净
1. 检查边刷/主刷磨损情况
2. 检查尘盒是否已满
3. 确认吸力模式（安静/标准/强力）
4. 检查滤网是否需要更换

### 无法回充
1. 充电座指示灯是否亮
2. 充电座周围是否有障碍物
3. 设备红外传感器是否脏污
4. 尝试手动对齐充电触点

### 噪音过大
1. 检查主刷/边刷是否有异物缠绕
2. 检查滚轮是否卡住
3. 确认尘盒安装到位
4. 检查是否在强力模式下运行

### 地图丢失
1. 检查是否在重新建图模式
2. 确认激光雷达无遮挡
3. 尝试保存当前地图后重新建图
4. 检查App版本和固件是否最新
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
4. 保存即可

## Wi-Fi 连接
1. 确保路由器为2.4G频段（不支持5G）
2. 长按设备Wi-Fi键5秒进入配网模式
3. 在App中选择Wi-Fi并输入密码
4. 等待连接完成（约30秒）

## 清扫模式
- 安静模式: 低噪音，适合夜间
- 标准模式: 平衡清洁力和噪音
- 强力模式: 最大吸力，适合深度清洁
- 拖地模式: 需要安装水箱和拖布

## 维护保养
- 每次清扫后清空尘盒
- 每周清洁传感器和充电触点
- 每月清洗滤网
- 每3个月更换边刷
- 每6个月检查主刷磨损

## 支持语音助手
- 小爱同学: 在米家App中绑定
- 天猫精灵: 在阿里智能App中添加设备
- 小度: 在小度App中搜索添加

## 支持功能
- 支持多层地图: 最多保存3张地图
- 支持虚拟墙: 在App中设置禁区和虚拟墙
- 支持断点续扫: 电量低自动回充，充满后继续清扫
- 支持地毯增压: 检测到地毯自动增大吸力
- 支持悬崖传感器: 自动检测楼梯边缘防跌落

## 电压规格
- 输入: 220V-240V / 50-60Hz
- 输出: 20V / 1.2A
- 电池: 5200mAh 锂电池
- 充电时间: 约4-5小时
- 续航时间: 约150分钟（标准模式）

## 规格参数
- 尺寸: 350 x 350 x 97 mm
- 重量: 3.8 kg
- 尘盒容量: 450 ml
- 水箱容量: 250 ml
- 噪音: ≤65 dB(A)
- 越障高度: ≤20 mm
""",
}


def init_vector_store(docs_dir: str = None, drop_existing: bool = False):
    """初始化向量库 — 完整流程

    Args:
        docs_dir: 知识文档目录路径，默认 data/knowledge/
        drop_existing: 是否删除已有集合重建
    """
    # 1. 连接 Milvus
    host = settings.milvus_host
    port = settings.milvus_port
    collection_name = settings.milvus_collection

    print(f"[InitVector] 连接 Milvus: {host}:{port}")
    connections.connect(host=host, port=port)

    # 2. 是否是删旧建新
    if drop_existing and utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        print(f"[InitVector] 已删除旧集合: {collection_name}")

    # 3. 获取 embedding 模型
    embedding = get_embedding()

    # 4. 创建集合
    collection = create_collection(collection_name, dim=embedding.dimension)

    # 5. 读取文档
    docs_dir = docs_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "knowledge"
    )

    documents = read_documents(docs_dir)

    # 6. 如果没有文档，使用默认知识
    if not documents:
        print("[InitVector] 知识目录为空，使用内置默认知识")
        documents = []
        for category, content in DEFAULT_KNOWLEDGE.items():
            paragraphs = content.strip().split("\n\n")
            for i, para in enumerate(paragraphs):
                para = para.strip()
                if len(para) < 10:
                    continue
                # 提取标题
                title = category
                for line in para.split("\n"):
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                documents.append(
                    {
                        "content": para,
                        "source": f"builtin/{category}.md",
                        "title": title,
                        "category": category,
                        "chunk_index": i,
                    }
                )

    # 7. 智能切分 (根据文档类型自动选择策略)
    splitter = SmartDocumentSplitter(chunk_size=500, chunk_overlap=50, embedding_model=embedding)
    chunks = []
    for doc in documents:
        doc_type = splitter.detect_type(doc.get("source", ""), doc.get("content", ""))
        sub = splitter.split(
            doc["content"],
            doc_type,
            {"source": doc["source"], "title": doc["title"], "category": doc["category"]},
        )
        chunks.extend(sub)

    # 8. 插入
    insert_to_milvus(collection, chunks, embedding)

    # 9. 加载集合到内存
    collection.load()
    print(f"[InitVector] 集合已加载，当前条目数: {collection.num_entities}")

    connections.disconnect("default")
    print("[InitVector] 全部完成")


if __name__ == "__main__":
    init_vector_store()
