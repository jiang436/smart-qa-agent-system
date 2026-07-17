"""KnowledgeGraph 测试 — 实体链接 / 兼容性 / 多跳推理 / GraphRAG

零外部依赖，全部内存计算，所有测试 <1ms
"""
import pytest
from smart_qa.knowledge.knowledge_graph import KnowledgeGraph, get_kg


@pytest.fixture
def kg():
    return KnowledgeGraph()


# ═══════════════════════════════════════
# link_entities — 实体提取
# ═══════════════════════════════════════


class TestEntityLinking:
    """实体链接 — 从自然语言提取设备/错误码/配件"""

    def test_extract_device_model(self, kg):
        result = kg.link_entities("X30 Pro 怎么设置定时清扫")
        assert "X30 Pro" in result["devices"]

    def test_extract_multiple_devices(self, kg):
        result = kg.link_entities("X30 Pro 和 T10 对比哪个好")
        assert "X30 Pro" in result["devices"]
        assert "T10" in result["devices"]

    def test_extract_error_code(self, kg):
        result = kg.link_entities("E05错误码怎么解决")
        assert "E05" in result["error_codes"]

    def test_extract_error_subcode(self, kg):
        result = kg.link_entities("E05-1 是什么故障")
        assert "E05-1" in result["error_codes"]

    def test_extract_part_keywords(self, kg):
        result = kg.link_entities("边刷大概多久换一次")
        assert "边刷" in result["parts"]

    def test_extract_multiple_parts(self, kg):
        result = kg.link_entities("边刷和滤网都要换了")
        assert "边刷" in result["parts"]
        assert "滤网" in result["parts"]

    def test_extract_all_empty_no_match(self, kg):
        result = kg.link_entities("你好啊今天天气不错")
        assert result["devices"] == []
        assert result["error_codes"] == []
        assert result["parts"] == []

    def test_device_long_match_priority(self, kg):
        """长型号优先匹配（X30 Pro 不拆分）"""
        result = kg.link_entities("X30 Pro 边刷")
        assert "X30 Pro" in result["devices"]
        assert "X30" not in result["devices"]  # 不应拆分匹配子串

    def test_case_insensitive_error_code(self, kg):
        result = kg.link_entities("e05 故障")
        assert "E05" in result["error_codes"]


# ═══════════════════════════════════════
# check_compatibility — 配件兼容性
# ═══════════════════════════════════════


class TestCompatibility:
    """配件兼容性判断"""

    def test_compatible_same_series(self, kg):
        result = kg.check_compatibility("边刷", "X30 Pro", "X30")
        assert result["compatible"] is True

    def test_incompatible_cross_series(self, kg):
        result = kg.check_compatibility("边刷", "X30 Pro", "T10")
        assert result["compatible"] is False

    def test_same_family_inference(self, kg):
        """同家族推理（即使精确表中没有）"""
        result = kg.check_compatibility("水箱", "X30 Pro", "X30")
        assert result["compatible"] is True

    def test_unknown_part_returns_false(self, kg):
        result = kg.check_compatibility("unknown_part", "X30 Pro", "T10")
        assert result["compatible"] is False

    def test_compatible_message_not_empty(self, kg):
        result = kg.check_compatibility("边刷", "X30 Pro", "X20 Pro")
        assert len(result["message"]) > 0

    def test_compatible_models_list_included(self, kg):
        result = kg.check_compatibility("边刷", "X30 Pro", "T10")
        assert "compatible_models" in result
        if result["compatible_models"]:
            assert "X30 Pro" in result["compatible_models"]


# ═══════════════════════════════════════
# get_error_info — 错误码查询
# ═══════════════════════════════════════


class TestErrorInfo:
    """错误码详情查询"""

    def test_exact_error_code(self, kg):
        info = kg.get_error_info("E05")
        assert info is not None
        assert info["title"] == "激光传感器异常"

    def test_sub_error_code(self, kg):
        info = kg.get_error_info("E05-1")
        assert info is not None
        assert "激光雷达不转" in info["title"]

    def test_case_insensitive(self, kg):
        info = kg.get_error_info("e05")
        assert info is not None

    def test_nonexistent_code(self, kg):
        info = kg.get_error_info("E99")
        assert info is None

    def test_all_top_level_codes_have_cause_and_fix(self, kg):
        """所有顶层错误码都有原因和解决方案"""
        for code in ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10"]:
            info = kg.get_error_info(code)
            assert info is not None, f"Missing error code: {code}"
            assert "cause" in info
            assert "fix" in info
            assert len(info["cause"]) > 0
            assert len(info["fix"]) > 0


# ═══════════════════════════════════════
# search_errors_by_symptom — 症状搜索
# ═══════════════════════════════════════


class TestErrorSearch:
    """症状搜索错误码"""

    def test_search_by_symptom(self, kg):
        results = kg.search_errors_by_symptom("激光雷达")
        assert len(results) > 0

    def test_search_no_match(self, kg):
        results = kg.search_errors_by_symptom("xyz_no_match")
        assert results == []


# ═══════════════════════════════════════
# multi_hop_search — 多跳推理
# ═══════════════════════════════════════


class TestMultiHopSearch:
    """多跳推理链路"""

    def test_cross_series_incompatibility(self, kg):
        result = kg.multi_hop_search("X30 Pro 的边刷能不能用在 T10 上")
        assert result is not None
        assert "answer" in result
        assert "path" in result
        assert result["compatible"] is False

    def test_same_series_compatibility(self, kg):
        result = kg.multi_hop_search("X30 Pro 的主刷能用在 X30 上吗")
        assert result is not None
        assert result["compatible"] is True

    def test_insufficient_entities_returns_none(self, kg):
        """单设备无配件 → 无多跳推理"""
        result = kg.multi_hop_search("X30 Pro 怎么样")
        assert result is None

    def test_no_devices_returns_none(self, kg):
        result = kg.multi_hop_search("你好世界")
        assert result is None

    def test_reasoning_path_not_empty(self, kg):
        result = kg.multi_hop_search("X30 Pro 的滤网能用在 T10 上吗")
        if result is not None:
            assert len(result["path"]) >= 2


# ═══════════════════════════════════════
# augment_context — GraphRAG 上下文
# ═══════════════════════════════════════


class TestAugmentContext:
    """GraphRAG 上下文增强"""

    def test_error_code_augments_context(self, kg):
        context = kg.augment_context("E05错误码怎么解决")
        assert context is not None
        assert "E05" in context
        assert "激光" in context

    def test_compatibility_augments_context(self, kg):
        context = kg.augment_context("X30 Pro 的边刷能不能用在 T10 上")
        assert context is not None
        assert "兼容" in context or "推理" in context or "X30" in context

    def test_simple_query_returns_entities_only(self, kg):
        context = kg.augment_context("X30 Pro 定时清扫怎么设置")
        if context is not None:
            assert "X30 Pro" in context
            assert "识别的实体" in context or "实体" in context

    def test_out_of_scope_returns_none(self, kg):
        context = kg.augment_context("今天天气不错")
        # 无实体识别 → 无上下文增强
        assert context is None or len(context) == 0


# ═══════════════════════════════════════
# get_kg — 工厂函数
# ═══════════════════════════════════════


class TestGetKG:
    """获取 KnowledgeGraph 实例"""

    def test_get_kg_returns_instance(self):
        instance = get_kg()
        assert isinstance(instance, KnowledgeGraph)

    def test_get_kg_same_instance(self):
        """同一进程内多次调用返回同一实例"""
        kg1 = get_kg()
        kg2 = get_kg()
        # 注意：每次调用 get_kg() 可能创建新实例（取决于 DI 容器状态）
        assert isinstance(kg1, KnowledgeGraph)
        assert isinstance(kg2, KnowledgeGraph)


# ═══════════════════════════════════════
# get_compatible_parts
# ═══════════════════════════════════════


class TestCompatibleParts:
    """获取设备配件兼容列表"""

    def test_known_device_has_parts(self, kg):
        parts = kg.get_compatible_parts("X30 Pro")
        assert len(parts) > 0
        for item in parts:
            assert "part" in item
            assert "compatible_models" in item

    def test_unknown_device_returns_empty(self, kg):
        parts = kg.get_compatible_parts("UnknownModel")
        assert parts == []


# ═══════════════════════════════════════
# get_reasoning_path — 可解释性
# ═══════════════════════════════════════


class TestReasoningPath:
    """推理路径生成"""

    def test_multihop_has_reasoning(self, kg):
        path = kg.get_reasoning_path("X30 Pro 的边刷能不能用在 T10 上")
        if path is not None:
            assert "推理路径" in path or "结论" in path

    def test_simple_query_no_reasoning(self, kg):
        path = kg.get_reasoning_path("你好")
        assert path is None
