"""评测数据集 — 小米米家扫拖机器人智能助手测试用例"""

TEST_CASES: list[dict] = [
    # ═══ QA — 产品参数 ═══
    {"query": "小米6 Max吸力多大", "expected_intent": "qa", "expected_keywords": ["吸力", "Pa"], "scenario": "qa", "difficulty": "easy"},
    {"query": "小米最便宜的扫拖机器人是哪款", "expected_intent": "qa", "expected_keywords": ["便宜", "元"], "scenario": "qa", "difficulty": "easy"},
    {"query": "小米和石头扫地机器人哪个好", "expected_intent": "qa", "expected_keywords": ["小米", "石头"], "scenario": "qa", "difficulty": "medium"},
    {"query": "2000以内推荐哪款扫地机", "expected_intent": "qa", "expected_keywords": ["2000", "推荐"], "scenario": "qa", "difficulty": "medium"},

    # ═══ QA — 使用操作 ═══
    {"query": "新买的米家扫地机怎么配网", "expected_intent": "qa", "expected_keywords": ["配网", "WiFi"], "scenario": "qa", "difficulty": "easy"},
    {"query": "怎么设置定时清扫", "expected_intent": "qa", "expected_keywords": ["定时", "清扫"], "scenario": "qa", "difficulty": "easy"},
    {"query": "怎么设置禁区不让扫地机进去", "expected_intent": "qa", "expected_keywords": ["禁区"], "scenario": "qa", "difficulty": "medium"},
    {"query": "扫地机支持5G WiFi吗", "expected_intent": "qa", "expected_keywords": ["5G", "2.4G"], "scenario": "qa", "difficulty": "medium"},

    # ═══ QA — 养护耗材 ═══
    {"query": "边刷和滤网分别多久换一次", "expected_intent": "qa", "expected_keywords": ["边刷", "滤网", "个月"], "scenario": "qa", "difficulty": "easy"},
    {"query": "原厂滤网和第三方滤网有什么区别", "expected_intent": "qa", "expected_keywords": ["原厂", "第三方", "滤网"], "scenario": "qa", "difficulty": "medium"},
    {"query": "基站污水盘怎么清洗", "expected_intent": "qa", "expected_keywords": ["基站", "清洗"], "scenario": "qa", "difficulty": "medium"},
    {"query": "HEPA滤网可以水洗吗", "expected_intent": "qa", "expected_keywords": ["滤网", "水洗"], "scenario": "qa", "difficulty": "hard"},

    # ═══ QA — 场景适配 ═══
    {"query": "养猫家庭用扫地机要注意什么", "expected_intent": "qa", "expected_keywords": ["宠物", "猫"], "scenario": "qa", "difficulty": "medium"},
    {"query": "实木地板拖地用什么水量", "expected_intent": "qa", "expected_keywords": ["木地板", "水量"], "scenario": "qa", "difficulty": "medium"},
    {"query": "回南天扫地机怎么用", "expected_intent": "qa", "expected_keywords": ["回南天", "烘干"], "scenario": "qa", "difficulty": "hard"},

    # ═══ QA — 智能联动 ═══
    {"query": "小爱同学能控制扫地机吗", "expected_intent": "qa", "expected_keywords": ["小爱", "语音"], "scenario": "qa", "difficulty": "easy"},
    {"query": "怎么设置离家自动清扫", "expected_intent": "qa", "expected_keywords": ["离家", "自动"], "scenario": "qa", "difficulty": "medium"},

    # ═══ QA — 售后 ═══
    {"query": "小米扫地机保修多久", "expected_intent": "qa", "expected_keywords": ["保修", "年"], "scenario": "qa", "difficulty": "easy"},
    {"query": "电池坏了能免费换吗", "expected_intent": "qa", "expected_keywords": ["电池", "免费"], "scenario": "qa", "difficulty": "medium"},

    # ═══ Troubleshoot ═══
    {"query": "错误码03悬崖传感器异常怎么办", "expected_intent": "troubleshoot", "expected_keywords": ["错误", "传感器"], "scenario": "troubleshoot", "difficulty": "easy"},
    {"query": "扫地机不走了显示E05", "expected_intent": "troubleshoot", "expected_keywords": ["E05", "故障"], "scenario": "troubleshoot", "difficulty": "easy"},
    {"query": "地图突然丢了要重新建", "expected_intent": "troubleshoot", "expected_keywords": ["地图", "建图"], "scenario": "troubleshoot", "difficulty": "medium"},
    {"query": "回充一直找不到充电座在转圈", "expected_intent": "troubleshoot", "expected_keywords": ["回充", "充电"], "scenario": "troubleshoot", "difficulty": "medium"},
    {"query": "扫地机以前能扫2小时现在40分钟就没电", "expected_intent": "troubleshoot", "expected_keywords": ["续航", "电池"], "scenario": "troubleshoot", "difficulty": "medium"},
    {"query": "拖完地全是灰色水渍比不拖还脏", "expected_intent": "troubleshoot", "expected_keywords": ["拖地", "水渍"], "scenario": "troubleshoot", "difficulty": "hard"},

    # ═══ Consumables ═══
    {"query": "边刷该换了买什么型号", "expected_intent": "consumables", "expected_keywords": ["边刷", "型号"], "scenario": "consumables", "difficulty": "easy"},
    {"query": "官方滤网多少钱哪里买", "expected_intent": "consumables", "expected_keywords": ["滤网", "价格"], "scenario": "consumables", "difficulty": "easy"},
    {"query": "拖布原厂和第三方哪个好", "expected_intent": "consumables", "expected_keywords": ["拖布", "原厂"], "scenario": "consumables", "difficulty": "medium"},

    # ═══ Device Control ═══
    # 设备控制是指令型查询，不依赖关键词匹配——评测时使用 expected_actions 验证
    {"query": "开始清扫", "expected_intent": "device_control",
     "expected_keywords": ["开始"], "expected_actions": ["start_cleaning"],
     "scenario": "device_control", "difficulty": "easy"},
    {"query": "检查我的设备状态", "expected_intent": "device_control",
     "expected_keywords": ["状态"], "expected_actions": ["get_device_status"],
     "scenario": "device_control", "difficulty": "easy"},
    {"query": "回去充电", "expected_intent": "device_control",
     "expected_keywords": ["充电"], "expected_actions": ["return_to_charge"],
     "scenario": "device_control", "difficulty": "easy"},
    {"query": "每天8点清扫客厅", "expected_intent": "device_control",
     "expected_keywords": ["定时"], "expected_actions": ["create_schedule"],
     "scenario": "device_control", "difficulty": "medium"},

    # ═══ SQL Query ═══
    {"query": "有多少用户绑定了X30 Pro", "expected_intent": "sql_query", "expected_keywords": ["用户"], "scenario": "sql_query", "difficulty": "medium"},
    {"query": "最近7天有多少次对话", "expected_intent": "sql_query", "expected_keywords": ["对话"], "scenario": "sql_query", "difficulty": "medium"},

    # ═══ General ═══
    {"query": "你好", "expected_intent": "general", "expected_keywords": [], "scenario": "general", "difficulty": "easy"},
    {"query": "今天天气怎么样", "expected_intent": "general", "expected_keywords": [], "scenario": "general", "difficulty": "easy", "note": "越界问题应拒绝"},
]


def get_test_cases(scenario=None, difficulty=None):
    cases = TEST_CASES
    if scenario:
        cases = [c for c in cases if c.get("scenario") == scenario]
    if difficulty:
        cases = [c for c in cases if c.get("difficulty") == difficulty]
    return cases


def get_stats():
    total = len(TEST_CASES)
    by_scenario, by_difficulty = {}, {}
    for c in TEST_CASES:
        s = c.get("scenario", "unknown")
        d = c.get("difficulty", "unknown")
        by_scenario[s] = by_scenario.get(s, 0) + 1
        by_difficulty[d] = by_difficulty.get(d, 0) + 1
    return {"total_cases": total, "by_scenario": by_scenario, "by_difficulty": by_difficulty}
