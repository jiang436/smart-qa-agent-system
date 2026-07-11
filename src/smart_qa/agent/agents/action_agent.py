"""Action Agent — MCP 工具调用执行

职责: 解析用户意图 -> 调用外部工具 -> 格式化结果 -> 返回

核心流程:
  1. 从 state 提取用户最新消息
  2. 解析用户意图（LLM / 关键词降级）
  3. 校验工具参数
  4. 调用 MCP 工具（带重试）
  5. 格式化结果为自然语言
  6. 写入 state

涉及技术:
  - MCP (Model Context Protocol) 工具调用
  - 意图解析: LLM 优先，关键词降级方案
  - 参数校验: 类型 / 必填 / 范围
  - 重试机制: 失败自动重试 1 次
"""

import json

from smart_qa.observability.logger import logger


class ActionAgent:
    """Action Agent: 工具调用执行器"""

    # 工具定义: 名称 -> { "description": ..., "parameters": {...} }
    # 通过 MCP 客户端自动发现工具
    tool_definitions: dict = {}

    def __init__(self, mcp_client=None, llm_client=None):
        """
        Args:
            mcp_client: MCP 客户端（用于调用工具）
            llm_client: LLM 客户端（用于意图解析）
        """
        self.mcp = mcp_client
        self.llm = llm_client
        self._tools_ready = False

    def _ensure_tools_ready(self):
        """确保工具已从 MCP Server 发现"""
        if not self._tools_ready and self.mcp:
            try:
                tools = self.mcp.discover_tools()
                self.tool_definitions = {t["name"]: t for t in tools}
                self._tools_ready = True
                logger.info("MCP 工具发现完成 count={}", len(tools))
            except Exception as e:
                logger.warning("MCP 工具发现失败: {}", e)

    async def execute_tool(self, state: dict) -> dict:
        """执行工具调用节点

        Args:
            state: AgentState 字典

        Returns:
            更新后的 state（final_answer 已填充工具结果）
        """
        query = self._extract_query(state)
        if not query:
            state["final_answer"] = "请描述您需要什么帮助？"
            return state

        self._ensure_tools_ready()
        if not self.tool_definitions:
            state["final_answer"] = "抱歉，当前没有可用的辅助工具。请描述您的问题，我会尽力直接解答。"
            return state

        # 1. 解析意图: 提取工具名和参数
        tool_name, args = await self._parse_tool_intent(query)

        if not tool_name:
            logger.info("ActionAgent 未解析到工具调用意图 query={}", query[:60])
            state["final_answer"] = "好的，收到您的问题。由于没有匹配的辅助工具，我直接回答您。"
            return state

        # 2. 参数校验
        validation = self._validate_args(tool_name, args)
        if not validation["valid"]:
            state["final_answer"] = f"参数格式有误: {validation['error']}\n请检查后重试，或换个方式描述您的需求。"
            return state

        # 3. 调用 MCP 工具
        server_name = self.tool_definitions[tool_name].get("server", "default")
        result = self._call_tool_with_retry(server_name, tool_name, args)

        if result is None:
            state["final_answer"] = f"调用 {tool_name} 工具失败，请稍后重试。"
            return state

        # 4. 格式化结果
        answer = self._format_result(tool_name, args, result)
        state["final_answer"] = answer

        # 记录工具调用历史（防循环检测用）
        tool_call = f"{tool_name}({json.dumps(args, ensure_ascii=False)})"
        history = state.get("tool_calls_history", [])
        history.append(tool_call)
        state["tool_calls_history"] = history

        logger.info("工具调用完成 tool={} args={}", tool_name, str(args)[:50])
        return state

    def _extract_query(self, state: dict) -> str:
        """提取用户最新消息"""
        messages = state.get("messages", [])
        if not messages:
            return ""

        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                return msg.content
            elif isinstance(msg, dict) and msg.get("role") in ("user", "human"):
                return msg.get("content", "")

        last = messages[-1]
        if hasattr(last, "content"):
            return last.content
        return str(last) if last else ""

    async def _parse_tool_intent(self, query: str) -> tuple:
        """解析用户意图，提取工具名和参数

        Returns:
            (tool_name, args) or (None, {})
        """
        if self.llm:
            return await self._llm_parse(query)
        return self._keyword_parse(query)

    async def _llm_parse(self, query: str) -> tuple:
        """使用 LLM 解析工具调用意图"""
        tools_desc = "\n".join(
            f"- {name}: {info['description']}, 参数: {info['parameters']}"
            for name, info in self.tool_definitions.items()
        )

        prompt = (
            f"用户输入: {query}\n\n"
            f"可用工具:\n{tools_desc}\n\n"
            "请判断用户是否需要调用工具。如果需要，输出 JSON 格式:\n"
            '{"tool": "工具名", "args": {"参数": "值"}}\n'
            "如果不需要调用任何工具，输出:\n"
            '{"tool": null, "args": {}}\n'
            "只输出 JSON，不要输出其他内容。"
        )

        try:
            import json

            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            content = content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.split("```")[0].strip()

            data = json.loads(content)
            tool_name = data.get("tool")
            tool_args = data.get("args", {})

            if tool_name and tool_name in self.tool_definitions:
                return tool_name, tool_args
            return None, {}

        except Exception as e:
            logger.warning("LLM 解析失败: {}", e)
            return self._keyword_parse(query)

    def _keyword_parse(self, query: str) -> tuple:
        """基于关键词的意图解析（无 LLM 时的降级方案）"""
        query_lower = query.lower()

        for name, info in self.tool_definitions.items():
            keywords = info.get("keywords", [name])
            if any(kw in query_lower for kw in keywords):
                args = {}
                params = info.get("parameters", {})
                for param_name, param_info in params.items():
                    default = param_info.get("default")
                    if default is not None:
                        args[param_name] = default
                return name, args

        return None, {}

    def _validate_args(self, tool_name: str, args: dict) -> dict:
        """校验工具参数"""
        params = self.tool_definitions.get(tool_name, {}).get("parameters", {})

        for pname, pinfo in params.items():
            # 必填项检查
            if pinfo.get("required", False) and pname not in args:
                return {"valid": False, "error": f"缺少必填参数 '{pname}'"}
            # 类型检查
            expected_type = pinfo.get("type", "string")
            if pname in args and args[pname] is not None:
                actual_type = type(args[pname]).__name__
                if expected_type == "number" and actual_type not in ("int", "float"):
                    return {"valid": False, "error": f"参数 '{pname}' 应为 {expected_type} 类型"}
                elif expected_type == "string" and actual_type != "str":
                    return {"valid": False, "error": f"参数 '{pname}' 应为 {expected_type} 类型"}

        return {"valid": True, "error": ""}

    def _call_tool_with_retry(self, server: str, tool_name: str, args: dict, max_retries: int = 1) -> str | None:
        """执行 MCP 工具调用，支持重试"""
        for attempt in range(max_retries + 1):
            try:
                result = self.mcp.call_tool(server, tool_name, args)
                logger.info("工具调用成功 tool={} attempt={}", tool_name, attempt + 1)
                return result
            except Exception as e:
                logger.warning("工具调用失败 tool={} attempt={} err={}", tool_name, attempt + 1, str(e))
                if attempt < max_retries:
                    continue
                return None
        return None

    def _format_result(self, tool_name: str, args: dict, result: str | None) -> str:
        """格式化工具执行结果为用户友好的回答"""
        if result is None:
            return f"抱歉，{tool_name} 工具调用返回了空结果。"

        return f"已为您查询到相关信息:\n\n{result}"
