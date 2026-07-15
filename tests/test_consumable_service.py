"""耗材服务测试"""

from smart_qa.services.consumable_service import ConsumableService


class TestConsumableService:
    def setup_method(self):
        self.service = ConsumableService()

    def test_identify_part_by_keyword(self):
        assert self.service.identify_part("边刷") == "side_brush"
        assert self.service.identify_part("滤网") == "hepa_filter"
        assert self.service.identify_part("拖布") == "mop"

    def test_identify_part_unknown(self):
        assert self.service.identify_part("随机内容") is None

    def test_get_product_exists(self):
        product = self.service.get_product("side_brush")
        assert product is not None
        assert product["name"] == "X30 Pro 原装边刷"
        assert product["price"] == 29.9

    def test_get_product_not_exists(self):
        assert self.service.get_product("unknown_part") is None

    def test_get_all_categories(self):
        cats = self.service.get_all_categories()
        assert "清洁刷组" in cats
        assert "拖地配套" in cats
        assert "套装优惠" in cats
        assert len(cats) >= 5

    def test_search_finds_results(self):
        results = self.service.search("边刷")
        assert len(results) >= 1
        assert any("边刷" in r["name"] for r in results)

    def test_search_no_results(self):
        results = self.service.search("zzzzznotexist")
        assert len(results) == 0
