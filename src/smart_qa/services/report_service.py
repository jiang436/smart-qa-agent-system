"""报告服务

提取自 agent/report_agent.py 中的报告生成逻辑。
"""


class ReportService:
    """报告生成服务

    提供:
      - 月度/周度使用报告
      - 异常事件汇总
      - 耗材更换提醒
      - 优化建议生成
    """

    def __init__(self, llm_client=None, db_client=None):
        self.llm = llm_client
        self.db = db_client

    async def generate_report(self, user_id: str, report_type: str = "monthly", days: int = 30) -> str:
        """生成报告主入口"""
        if report_type == "monthly":
            return await self._monthly_report(user_id, days)
        elif report_type == "weekly":
            return await self._monthly_report(user_id, 7)
        elif report_type == "abnormal":
            return await self._abnormal_report(user_id, days)
        elif report_type == "consumable":
            return await self._consumable_reminder(user_id)
        return await self._monthly_report(user_id, days)

    async def _monthly_report(self, user_id: str, days: int) -> str:
        """月度使用报告"""
        stats = {}
        if self.db:
            try:
                stats = await self.db.get_usage_stats(user_id, days)
            except Exception:
                pass

        if not stats or stats.get("total_cleans", 0) == 0:
            return f"📊 使用报告 (近{days}天)\n暂无使用数据。请确认设备已绑定并正常使用。"

        parts = [
            f"📊 {'月度' if days >= 28 else '周度'}使用报告",
            "━━━━━━━━━━━━━━━━",
            "",
            f"📈 使用统计 ({days}天):",
            f"   • 清扫次数: {stats.get('total_cleans', 0)} 次",
            f"   • 清扫面积: {stats.get('total_area', 0)} m²",
            f"   • 累计时长: {stats.get('total_duration', 0)} 分钟",
            f"   • 平均每次: {stats.get('avg_area_per_clean', 0)} m²",
        ]

        error_count = stats.get("error_count", 0)
        if error_count > 0:
            parts.append(f"   • ⚠️ 异常次数: {error_count} 次")
            parts.append("\n💡 建议: 检查设备轮子和边刷是否有缠绕物，异常频繁时联系售后。")

        return "\n".join(parts)

    async def _abnormal_report(self, user_id: str, days: int) -> str:
        """异常事件报告"""
        return (
            f"⚠️ 异常事件报告 (近{days}天)\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"常见异常及处理:\n"
            f"  E01-E03: 检查传感器和轮子\n"
            f"  E05: 电池过热，移至阴凉处\n"
            f"  E06: 清洁激光雷达\n"
            f"  E07: 重新配网\n\n"
            f"频繁异常建议联系售后。"
        )

    async def _consumable_reminder(self, user_id: str) -> str:
        """耗材提醒"""
        return (
            "🔧 耗材更换提醒\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "建议定期检查以下耗材:\n"
            "  • 边刷: 每 3-6 个月\n"
            "  • 主刷: 每 6-12 个月\n"
            "  • HEPA滤网: 每 3-4 个月\n"
            "  • 拖布: 每 2-3 个月\n\n"
            "需要购买耗材？我可以帮您推荐兼容型号。"
        )
