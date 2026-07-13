"""评测数据集 — 扫地机器人智能助手测试用例

使用方式:
    from smart_qa.evaluation.dataset import get_test_cases, get_stats

    cases = get_test_cases(scenario="qa")       # 筛选场景
    cases = get_test_cases(difficulty="hard")    # 筛选难度
    stats = get_stats()                          # 数据集统计
"""

TEST_CASES: list[dict] = [
    # ── QA 场景 ──
    {
        "query": "X30 Pro 怎么设置定时清扫",
        "expected_intent": "qa",
        "expected_keywords": ["X30 Pro", "定时", "清扫"],
        "scenario": "qa",
        "difficulty": "easy",
        "description": "基础功能询问",
    },
    {
        "query": "扫地机器人支持多大的电压",
        "expected_intent": "qa",
        "expected_keywords": ["电压"],
        "scenario": "qa",
        "difficulty": "easy",
    },
    {
        "query": "怎么重置Wi-Fi连接",
        "expected_intent": "qa",
        "expected_keywords": ["重置", "Wi-Fi", "连接"],
        "scenario": "qa",
        "difficulty": "medium",
    },
    {
        "query": "X30 Pro 能连接5G Wi-Fi吗",
        "expected_intent": "qa",
        "expected_keywords": ["5G", "Wi-Fi"],
        "scenario": "qa",
        "difficulty": "medium",
    },
    # ── Troubleshoot 场景 ──
    {
        "query": "扫地机器人不工作了怎么办",
        "expected_intent": "troubleshoot",
        "expected_keywords": ["不工作"],
        "scenario": "troubleshoot",
        "difficulty": "easy",
    },
    {
        "query": "显示E05错误码是什么意思",
        "expected_intent": "troubleshoot",
        "expected_keywords": ["E05", "错误码"],
        "scenario": "troubleshoot",
        "difficulty": "easy",
    },
    {
        "query": "扫地机一直响，指示灯红色",
        "expected_intent": "troubleshoot",
        "expected_keywords": ["响", "指示灯"],
        "scenario": "troubleshoot",
        "difficulty": "medium",
    },
    {
        "query": "为什么扫地机器人老是卡在门槛那里",
        "expected_intent": "troubleshoot",
        "expected_keywords": ["卡住", "门槛"],
        "scenario": "troubleshoot",
        "difficulty": "medium",
    },
    # ── Consumables 场景 ──
    {
        "query": "边刷该换了，买什么型号",
        "expected_intent": "consumables",
        "expected_keywords": ["边刷", "型号"],
        "scenario": "consumables",
        "difficulty": "easy",
    },
    {
        "query": "HEPA滤网多少钱",
        "expected_intent": "consumables",
        "expected_keywords": ["滤网", "价格"],
        "scenario": "consumables",
        "difficulty": "easy",
    },
    {
        "query": "X30 Pro 用什么拖布",
        "expected_intent": "consumables",
        "expected_keywords": ["拖布"],
        "scenario": "consumables",
        "difficulty": "medium",
    },
    # ── Device Control 场景 ──
    {
        "query": "开始清扫",
        "expected_intent": "device_control",
        "expected_keywords": ["清扫"],
        "scenario": "device_control",
        "difficulty": "easy",
    },
    {
        "query": "检查我的设备状态",
        "expected_intent": "device_control",
        "expected_keywords": ["状态"],
        "scenario": "device_control",
        "difficulty": "easy",
    },
    {
        "query": "回去充电",
        "expected_intent": "device_control",
        "expected_keywords": ["充电"],
        "scenario": "device_control",
        "difficulty": "medium",
    },
    # ── Report 场景 ──
    {
        "query": "生成我的使用报告",
        "expected_intent": "report",
        "expected_keywords": ["报告"],
        "scenario": "report",
        "difficulty": "easy",
    },
    {
        "query": "查看这个月的清洁统计",
        "expected_intent": "report",
        "expected_keywords": ["统计"],
        "scenario": "report",
        "difficulty": "medium",
    },
    # ── General 场景 ──
    {
        "query": "你好",
        "expected_intent": "general",
        "expected_keywords": [],
        "scenario": "general",
        "difficulty": "easy",
    },
    {
        "query": "今天天气怎么样",
        "expected_intent": "general",
        "expected_keywords": [],
        "scenario": "general",
        "difficulty": "easy",
        "note": "越界问题应拒绝",
    },
]


def get_test_cases(scenario: str | None = None, difficulty: str | None = None) -> list[dict]:
    """按条件筛选测试用例

    Args:
        scenario: qa / troubleshoot / consumables / device_control / report / general
        difficulty: easy / medium / hard

    Returns:
        匹配的测试用例列表
    """
    cases = TEST_CASES
    if scenario:
        cases = [c for c in cases if c.get("scenario") == scenario]
    if difficulty:
        cases = [c for c in cases if c.get("difficulty") == difficulty]
    return cases


def get_stats() -> dict:
    """数据集统计"""
    total = len(TEST_CASES)
    by_scenario: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    for c in TEST_CASES:
        s = c.get("scenario", "unknown")
        d = c.get("difficulty", "unknown")
        by_scenario[s] = by_scenario.get(s, 0) + 1
        by_difficulty[d] = by_difficulty.get(d, 0) + 1
    return {
        "total_cases": total,
        "by_scenario": by_scenario,
        "by_difficulty": by_difficulty,
    }
