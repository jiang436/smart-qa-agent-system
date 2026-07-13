"""Report Agent — 根据用户使用数据生成报告

自动生成周期性报告，帮助用户了解设备使用情况和耗材状态。

报告类型:
  1. 月度使用报告: 清扫次数/时长/面积/耗材消耗统计
  2. 异常汇总: 本月发生的故障/错误码统计
  3. 优化建议: 基于使用习惯的个性化建议
  4. 耗材提醒: 基于上次更换时间的耗材更换提醒

数据来源:
  - PostgreSQL: 设备使用记录 (DeviceUsageLog)
  - PostgreSQL: 耗材订单记录 (ConsumableOrder)
  - 记忆层: 用户画像和偏好
"""

from datetime import datetime

from smart_qa.observability.logger import logger


class ReportAgent:
    """报告生成 Agent

    用法:
        agent = ReportAgent(llm_client=llm, db_client=postgres_client)
        result = await agent.generate_report(state)
    """

    def __init__(self, llm_client=None, db_client=None):
        """
        Args:
            llm_client: LLM 客户端（用于生成报告总结）
            db_client: PostgresClient（数据来源）
        """
        self.llm = llm_client
        self.db = db_client

    async def generate_report(self, state: dict) -> dict:
        """根据 state 中的报告请求生成对应报告"""
        user_id = state.get("user_id", "unknown")
        report_type = state.get("task_memory", {}).get("report_type", "monthly")
        days = state.get("task_memory", {}).get("days", 30)

        if report_type == "monthly":
            report = await self.generate_monthly_report(user_id, days)
        elif report_type == "weekly":
            report = await self.generate_monthly_report(user_id, 7)
        elif report_type == "abnormal":
            report = await self.generate_abnormal_report(user_id, days)
        elif report_type == "consumable":
            report = await self.generate_consumable_reminder(user_id)
        else:
            report = await self.generate_monthly_report(user_id, days)

        state["final_answer"] = report
        return state

    async def generate_monthly_report(self, user_id: str, days: int = 30) -> str:
        """生成月度使用报告"""
        stats = {}
        if self.db:
            try:
                stats = await self.db.get_usage_stats(user_id, days)
            except Exception as e:
                logger.warning("获取统计数据失败: {}", e)

        if not stats or stats.get("total_cleans", 0) == 0:
            return self._empty_report(days)

        user_device = await self._get_user_device(user_id)
        consumable_status = await self._get_consumable_status(user_id)

        parts = [
            f"使用报告 ({'月度' if days >= 28 else '周度'})",
            "",
        ]

        if user_device:
            parts.append(f"设备: {user_device.get('device_model', '未知')}")
            parts.append(f"固件: {user_device.get('firmware_version', '未知')}")
            parts.append("")

        parts.append(f"使用统计 ({days}天):")
        parts.append(f"  - 清扫次数: {stats.get('total_cleans', 0)} 次")
        parts.append(f"  - 清扫面积: {stats.get('total_area', 0)} m2")
        parts.append(f"  - 累计时长: {stats.get('total_duration', 0)} 分钟")
        parts.append(f"  - 平均每次面积: {stats.get('avg_area_per_clean', 0)} m2")

        error_count = stats.get("error_count", 0)
        if error_count > 0:
            parts.append(f"  - 异常次数: {error_count} 次")
        parts.append("")

        if consumable_status:
            parts.append("耗材状态:")
            for part_name, info in consumable_status.items():
                days_ago = info.get("days_since_last", "未更换")
                suggested = info.get("suggested_days", 90)
                if isinstance(days_ago, int):
                    remaining = max(0, suggested - days_ago)
                    status = "正常" if remaining > 30 else ("即将到期" if remaining > 0 else "建议更换")
                    parts.append(f"  - {part_name}: {status} (距上次更换 {days_ago} 天, 建议 {suggested} 天)")
                else:
                    parts.append(f"  - {part_name}: 暂无更换记录")
            parts.append("")

        if self.llm and stats.get("total_cleans", 0) > 0:
            try:
                suggestions = await self._generate_suggestions(user_id, stats, user_device)
                if suggestions:
                    parts.append("优化建议:")
                    parts.append(suggestions)
            except Exception:
                pass

        return "\n".join(parts)

    async def generate_abnormal_report(self, user_id: str, days: int = 30) -> str:
        """生成异常汇总报告"""
        parts = [
            f"异常事件报告 (近{days}天)",
            "",
        ]

        if self.db:
            try:
                stats = await self.db.get_usage_stats(user_id, days)
                error_count = stats.get("error_count", 0)
            except Exception:
                error_count = 0
        else:
            error_count = 0

        if error_count == 0:
            parts.append(f"近{days}天无异常事件，设备运行良好！")
        else:
            parts.append(f"共发现 {error_count} 次异常事件:")
            parts.append("")
            parts.append("常见异常处理建议:")
            parts.append("  - E01/E02/E03: 检查轮子和边刷是否缠绕异物")
            parts.append("  - E05: 检查电池温度，将设备移至阴凉处")
            parts.append("  - E06: 清洁激光雷达传感器")
            parts.append("  - E07: 重新配对 Wi-Fi")
            parts.append("")
            parts.append("如问题频繁出现，建议联系售后检修。")

        return "\n".join(parts)

    async def generate_consumable_reminder(self, user_id: str) -> str:
        """生成耗材更换提醒"""
        parts = [
            "耗材更换提醒",
            "",
        ]

        consumable_status = await self._get_consumable_status(user_id)

        if not consumable_status:
            parts.append("暂无耗材更换记录。建议首次使用3个月后检查耗材磨损情况。")
        else:
            needs_replacement = False
            for part_name, info in consumable_status.items():
                days_ago = info.get("days_since_last")
                suggested = info.get("suggested_days", 90)

                if isinstance(days_ago, int):
                    remaining = max(0, suggested - days_ago)
                    if remaining <= 0:
                        parts.append(f"{part_name}: 已超期 {abs(remaining)} 天，建议立即更换！")
                        needs_replacement = True
                    elif remaining <= 15:
                        parts.append(f"{part_name}: 还剩 {remaining} 天，建议准备更换")
                        needs_replacement = True
                    else:
                        parts.append(f"{part_name}: 还剩 {remaining} 天，状态良好")
                else:
                    parts.append(f"{part_name}: 暂无更换记录，建议周期 {suggested} 天")

            if needs_replacement:
                parts.append("")
                parts.append("需要购买耗材？我可以帮您推荐兼容型号。")

        user_device = await self._get_user_device(user_id)
        if user_device:
            parts.insert(1, f"设备型号: {user_device.get('device_model', '未知')}")

        return "\n".join(parts)

    def _empty_report(self, days: int) -> str:
        """生成无数据时的空报告"""
        return (
            f"使用报告 (近{days}天)\n\n"
            f"暂无使用数据。\n"
            f"可能的原因:\n"
            f"  - 设备尚未绑定，请先绑定您的设备\n"
            f"  - 近期未使用设备清扫\n"
            f"  - 数据同步需要一些时间\n\n"
            f"使用设备后，下期报告将自动生成。"
        )

    async def _get_user_device(self, user_id: str) -> dict | None:
        """获取用户设备信息"""
        if not self.db:
            return {"device_model": "X30 Pro", "firmware_version": "v3.2.1"}

        try:
            device = await self.db.get_user_device(user_id)
            if device:
                return {
                    "device_model": device.device_model,
                    "device_name": device.device_name,
                    "firmware_version": device.firmware_version,
                    "bound_at": str(device.bound_at),
                }
        except Exception as e:
            logger.warning("获取设备信息失败: {}", e)
        return None

    async def _get_consumable_status(self, user_id: str) -> dict[str, dict]:
        """获取用户耗材更换状态"""
        result = {}

        consumables = {
            "边刷": ("side_brush", 90),
            "主刷": ("main_brush", 180),
            "HEPA滤网": ("filter", 120),
            "拖布": ("mop", 60),
        }

        for part_name, (part_type, suggested_days) in consumables.items():
            status = {"suggested_days": suggested_days, "days_since_last": "未更换"}
            if self.db:
                try:
                    last_order = await self.db.get_last_order(user_id, part_type)
                    if last_order:
                        days_ago = (datetime.utcnow() - last_order.ordered_at).days
                        status["days_since_last"] = days_ago
                        status["last_order"] = last_order.order_id
                        status["last_source"] = last_order.source
                except Exception:
                    pass
            result[part_name] = status
        return result

    async def _generate_suggestions(self, user_id: str, stats: dict, user_device: dict | None) -> str:
        """使用 LLM 生成个性化优化建议"""
        if not self.llm:
            return self._default_suggestions(stats)

        device_model = user_device.get("device_model", "未知") if user_device else "未知"
        total_cleans = stats.get("total_cleans", 0)
        total_area = stats.get("total_area", 0)
        avg_area = stats.get("avg_area_per_clean", 0)

        prompt = (
            f"基于以下扫地机器人使用数据，给用户提供 2-3 条简洁的优化建议:\n"
            f"- 设备型号: {device_model}\n"
            f"- 近30天清扫次数: {total_cleans} 次\n"
            f"- 累计清扫面积: {total_area} m2\n"
            f"- 平均每次面积: {avg_area} m2\n"
            f"\n要求: 建议要具体、可执行、针对数据给出。每条建议一行，用编号列出。"
        )

        try:
            response = await self.llm.ainvoke(prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning("LLM 建议生成失败: {}", e)
            return self._default_suggestions(stats)

    def _default_suggestions(self, stats: dict) -> str:
        """无 LLM 时的默认建议"""
        suggestions = []

        avg_area = stats.get("avg_area_per_clean", 0)
        total_cleans = stats.get("total_cleans", 0)

        if avg_area < 20 and total_cleans > 0:
            suggestions.append("1. 您的清扫面积较小，建议检查是否设置了虚拟墙限制了清扫范围")
        elif avg_area > 80:
            suggestions.append("1. 清扫面积较大，建议使用强力模式确保深度清洁")

        if total_cleans < 10:
            suggestions.append("2. 清扫频率较低，建议设置定时清扫保持地面清洁")

        suggestions.append("3. 定期清洁传感器和充电触点，保持设备最佳性能")

        return "\n".join(suggestions)
