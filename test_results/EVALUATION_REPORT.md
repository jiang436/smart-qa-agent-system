# RAG 评测报告

**时间**: 2026-07-17 14:13:57  |  **Ground Truth**: 12 条查询

## 📊 检索质量

| 指标 | 值 | 说明 |
|------|----|------|
| recall_at_3 | **0.75** | |
| recall_at_5 | **0.7917** | |
| precision_at_3 | **0.4444** | |
| precision_at_5 | **0.3833** | |
| mrr | **0.6472** | |
| hit_at_5 | **0.8333** | |
| keyword_coverage_at_5 | **0.8333** | |

### 各查询 MRR

- ✅ `X30 Pro 定时清扫怎么设置`: RR=1.0
- ✅ `E05错误码是什么故障`: RR=0.5
- ✅ `边刷多久换一次`: RR=0.5
- ✅ `HEPA滤网更换周期`: RR=1.0
- ✅ `扫地机连不上WiFi怎么办`: RR=1.0
- ✅ `扫地机器人回充失败`: RR=0.5
- ✅ `拖布发黄洗不干净了`: RR=1.0
- ✅ `X30 Pro 和 T10 对比哪个好`: RR=1.0
- ⚠️ `扫地机噪音太大怎么办`: RR=0.1
- ✅ `米家APP怎么绑定扫地机`: RR=0.5
- ✅ `耗材是买原装还是第三方`: RR=0.5
- ⚠️ `建图失败提示E06`: RR=0.1667

## ⚡ 性能

| 指标 | 值 |
|------|----|
| bm25_index.docs | 121 |
| bm25_index.terms | 6343 |
| bm25_index.avg_doc_len | 208.5 |
| bm25_index.index_size_kb | 180.2 |
| bm25_search_ms.avg_ms | 0.22 |
| bm25_search_ms.min_ms | 0.11 |
| bm25_search_ms.max_ms | 0.35 |
| bm25_search_ms.p50_ms | 0.23 |
| bm25_search_ms.p95_ms | 0.35 |
| bm25_search_ms.samples | 12 |
| bm25_throughput_qps | 4722.6 |
| full_pipeline_ms.avg | 0.7 |
| full_pipeline_ms.min | 0.2 |
| full_pipeline_ms.max | 3.5 |
| context_size.avg_chars | 1264.8 |
| context_size.avg_tokens | 316 |

## 💰 Token 追踪

- 系统 Prompt 总计: **1639 tokens**
- 预估每请求: **~2114 tokens**
- 知识库: 121 docs, ~11271 tokens

## 🎯 忠实性

- 自一致性: **1.0**
