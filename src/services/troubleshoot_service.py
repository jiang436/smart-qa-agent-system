"""故障排查服务 — 统一使用 TroubleshootScenario 中的决策树和错误码

本服务封装诊断逻辑，数据定义集中在 src/app/scenarios/troubleshoot_scenario.py，
避免两份决策树不同步的问题。
"""

import re

from src.app.scenarios.troubleshoot_scenario import DIAGNOSIS_TREE, ERROR_CODE_MAP


class TroubleshootService:
    """故障排查服务

    提供:
      - 错误码匹配诊断
      - 决策树引导式排查
      - 多轮对话进度追踪
    """

    MAX_DIAGNOSIS_ROUNDS = 5

    def lookup_error_code(self, code: str) -> dict | None:
        """查询错误码"""
        return ERROR_CODE_MAP.get(code.upper())

    def match_fault_type(self, query: str) -> str | None:
        """根据用户描述匹配故障分类"""
        mapping = {
            "不工作/不开机": ["不工作", "不开机", "没反应", "开不了", "死机"],
            "清扫不干净": ["不干净", "扫不", "漏扫", "灰尘"],
            "无法回充": ["回充", "充电", "回不去", "找不到充电"],
            "异常噪音": ["噪音", "太吵", "声音大", "异响", "咔咔"],
            "App 控制异常": ["app连不上", "无法远程", "手机控制不了", "app离线", "app", "应用控制"],
            "Wi-Fi 连接失败": ["wifi", "wi-fi", "联网", "连不上", "配网", "掉线"],
            "边刷异常": ["边刷不转", "边刷异响"],
            "开机无反应": ["开机没反应", "按了没反应", "开不起来", "启动不了"],
            "原地打转/不直走": ["原地", "打转", "转圈", "不直走", "走不直", "跑偏"],
            "拖地不出水/水量异常": ["不出水", "不拖地", "拖地没水", "拖地干", "渗水"],
            "基站漏水": ["漏水", "基站有水", "水箱漏"],
            "烘干功能异常": ["烘干", "不热", "不干", "烘干不热", "拖布湿"],
            "集尘异常": ["不集尘", "集尘失败", "尘盒不倒", "集尘无力"],
            "固件更新失败": ["更新失败", "升级失败", "固件"],
            "电池续航骤降": ["续航", "电池不耐用", "耗电快", "很快没电"],
        }
        q = query.lower()
        for fault, keywords in mapping.items():
            if any(kw in q for kw in keywords):
                return fault
        return None

    def get_diagnosis_tree(self, fault_type: str) -> dict | None:
        """获取故障类型的决策树"""
        return DIAGNOSIS_TREE.get(fault_type)

    def extract_error_code(self, text: str) -> str | None:
        """从文本中提取错误码"""
        match = re.search(r"[Ee](\d{2,3})", text)
        if match:
            code = f"E{match.group(1)}"
            return code if code in ERROR_CODE_MAP else None
        return None

    def is_positive_response(self, text: str) -> bool:
        """判断用户回答是否为肯定"""
        pos = ["是", "对", "有", "嗯", "好", "可以", "能", "亮", "正常", "yes", "y"]
        neg = ["不", "没", "无", "否", "没有", "不行", "不能", "no", "n"]
        t = text.strip().lower()
        for n in neg:
            if t.startswith(n) or t == n:
                return False
        for p in pos:
            if t.startswith(p) or t == p:
                return True
        return False
