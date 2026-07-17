"""RouterAgent 意图分类测试（关键词模式）"""
from smart_qa.agent.agents.router_agent import RouterAgent


class TestRouterAgent:
    def setup_method(self):
        self.router = RouterAgent()

    def test_classify_qa_keywords(self):
        assert self.router.classify("怎么设置定时清扫") == "qa"
        assert self.router.classify("X30 Pro 支持多大面积") == "qa"
        assert self.router.classify("如何重置Wi-Fi") == "qa"
        assert self.router.classify("说明书上说尘盒怎么清理") == "qa"

    def test_classify_troubleshoot_keywords(self):
        assert self.router.classify("机器不工作了") == "troubleshoot"
        assert self.router.classify("E05错误怎么解决") == "troubleshoot"
        assert self.router.classify("扫地机一直响停不下来") == "troubleshoot"
        assert self.router.classify("连不上Wi-Fi了") == "troubleshoot"

    def test_classify_general_default(self):
        assert self.router.classify("你好啊") == "general"
