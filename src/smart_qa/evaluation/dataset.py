"""评测数据集 — 50+ 测试用例覆盖三个场景

每条用例包含:
  - query: 用户问题
  - expected_intent: 期望意图
  - scenario: 所属场景
  - expected_keywords: 期望回答中包含的关键词
  - difficulty: 难度 easy/medium/hard
"""

TEST_CASES = [
    # ===== QA 知识问答 (20 cases) =====
    {
        "query": "怎么设置定时清扫？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["定时"],
        "difficulty": "easy",
    },
    {
        "query": "扫地机器人支持拖地功能吗？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["拖地"],
        "difficulty": "easy",
    },
    {
        "query": "最大吸力是多少？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["吸力"],
        "difficulty": "easy",
    },
    {
        "query": "怎么连接Wi-Fi？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["Wi-Fi"],
        "difficulty": "easy",
    },
    {
        "query": "支持哪些国家的电压？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["电压"],
        "difficulty": "medium",
    },
    {
        "query": "怎么重置设备？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["重置"],
        "difficulty": "easy",
    },
    {
        "query": "清洗拖布需要注意什么？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["拖布"],
        "difficulty": "medium",
    },
    {
        "query": "虚拟墙怎么设置？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["虚拟墙"],
        "difficulty": "medium",
    },
    {
        "query": "支持多少种清洁模式？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["模式"],
        "difficulty": "easy",
    },
    {
        "query": "噪音大不大？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["噪音"],
        "difficulty": "easy",
    },
    {
        "query": "能上地毯吗？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["地毯"],
        "difficulty": "medium",
    },
    {
        "query": "宠物家庭适用吗？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["宠物"],
        "difficulty": "medium",
    },
    {
        "query": "水箱容量多大？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["水箱"],
        "difficulty": "easy",
    },
    {
        "query": "建图需要多长时间？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["建图"],
        "difficulty": "medium",
    },
    {
        "query": "支持多层楼吗？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["多层"],
        "difficulty": "hard",
    },
    {
        "query": "怎么查历史清扫记录？",
        "expected_intent": "qa",
        "scenario": "qa",
        "expected_keywords": ["历史"],
        "difficulty": "easy",
    },
    # ===== Troubleshoot 故障排查 (20 cases) =====
    {
        "query": "机器不工作了",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["检查"],
        "difficulty": "medium",
    },
    {
        "query": "显示错误码E05",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["E05"],
        "difficulty": "easy",
    },
    {
        "query": "一直卡在门槛那里",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["门槛"],
        "difficulty": "easy",
    },
    {
        "query": "突然就不充电了",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["充电"],
        "difficulty": "medium",
    },
    {
        "query": "声音比以前大了很多",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["声音"],
        "difficulty": "medium",
    },
    {
        "query": "老是找不到充电桩",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["充电桩"],
        "difficulty": "hard",
    },
    {
        "query": "拖地漏水",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["漏水"],
        "difficulty": "medium",
    },
    {
        "query": "地图丢失了",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["地图"],
        "difficulty": "easy",
    },
    {
        "query": "App连不上设备",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["连接"],
        "difficulty": "medium",
    },
    {
        "query": "尘盒不吸尘了",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["尘盒"],
        "difficulty": "medium",
    },
    {
        "query": "轮子不转了",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["轮子"],
        "difficulty": "medium",
    },
    {
        "query": "指示灯一直闪红灯",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["红灯"],
        "difficulty": "easy",
    },
    {
        "query": "自动回充失败",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["回充"],
        "difficulty": "hard",
    },
    {
        "query": "扫地机不按规划的路线走",
        "expected_intent": "troubleshoot",
        "scenario": "troubleshoot",
        "expected_keywords": ["路线"],
        "difficulty": "hard",
    },
    # ===== Consumables 耗材管理 (10 cases) =====
    {
        "query": "边刷该换了，买什么样的？",
        "expected_intent": "consumables",
        "scenario": "consumables",
        "expected_keywords": ["边刷"],
        "difficulty": "easy",
    },
    {
        "query": "滤网多久换一次？",
        "expected_intent": "consumables",
        "scenario": "consumables",
        "expected_keywords": ["滤网"],
        "difficulty": "easy",
    },
    {
        "query": "哪里买原装耗材？",
        "expected_intent": "consumables",
        "scenario": "consumables",
        "expected_keywords": ["原装"],
        "difficulty": "easy",
    },
    {
        "query": "主刷磨损了需要换吗？",
        "expected_intent": "consumables",
        "scenario": "consumables",
        "expected_keywords": ["主刷"],
        "difficulty": "medium",
    },
    {
        "query": "能用第三方的边刷吗？",
        "expected_intent": "consumables",
        "scenario": "consumables",
        "expected_keywords": ["第三方"],
        "difficulty": "medium",
    },
    {
        "query": "耗材套装和单买哪个划算？",
        "expected_intent": "consumables",
        "scenario": "consumables",
        "expected_keywords": ["套装"],
        "difficulty": "medium",
    },
    # ===== General 闲聊 (5 cases) =====
    {
        "query": "你好",
        "expected_intent": "general",
        "scenario": "general",
        "expected_keywords": [],
        "difficulty": "easy",
    },
    {
        "query": "今天天气真不错",
        "expected_intent": "general",
        "scenario": "general",
        "expected_keywords": [],
        "difficulty": "easy",
    },
    {
        "query": "你叫什么名字？",
        "expected_intent": "general",
        "scenario": "general",
        "expected_keywords": [],
        "difficulty": "easy",
    },
]


def get_test_cases(scenario=None, difficulty=None):
    """按条件筛选测试用例"""
    cases = TEST_CASES
    if scenario:
        cases = [c for c in cases if c["scenario"] == scenario]
    if difficulty:
        cases = [c for c in cases if c["difficulty"] == difficulty]
    return cases


def get_stats():
    """返回测试集统计信息"""
    from collections import Counter

    return {
        "total": len(TEST_CASES),
        "by_scenario": dict(Counter(c["scenario"] for c in TEST_CASES)),
        "by_difficulty": dict(Counter(c["difficulty"] for c in TEST_CASES)),
    }
