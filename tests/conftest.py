"""共享 Fixtures — 测试用工具和 Mock"""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_docs():
    """通用测试文档列表"""
    return [
        {"content": "X30 Pro 扫地机器人电池过热保护，请将设备移至阴凉处", "score": 0.85, "source": "L1_semantic"},
        {"content": "如何重置扫地机器人Wi-Fi连接，长按重置键5秒", "score": 0.72, "source": "L1_semantic"},
        {"content": "边刷更换周期为3-6个月，建议定期检查磨损情况", "score": 0.68, "source": "L1_semantic"},
        {"content": "HEPA滤网建议每3-4个月更换一次，以保证过滤效果", "score": 0.65, "source": "L1_semantic"},
        {"content": "E05错误码表示电池过热，请冷却后重启设备", "score": 0.60, "source": "L1_semantic"},
        {"content": "拖布建议每2-3个月更换，干硬掉毛后拖地留水渍", "score": 0.55, "source": "L1_semantic"},
    ]


@pytest.fixture
def sample_query() -> str:
    return "电池过热怎么处理"
