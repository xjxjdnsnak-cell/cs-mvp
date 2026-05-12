import unittest

from demo_analysis.impact_engine.map_tactics import locate_area, load_map_areas, point_in_area, AreaInfo


class TestMapTactics(unittest.TestCase):
    def test_locate_top_mid(self):
        area = locate_area("de_mirage", -150, -700, 0)
        self.assertIsNotNone(area)
        self.assertEqual(area.name, "top_mid")

    def test_locate_connector(self):
        area = locate_area("de_mirage", -800, -25, 0)
        self.assertIsNotNone(area)
        self.assertEqual(area.name, "connector")

    def test_locate_window(self):
        area = locate_area("de_mirage", -1174, -744, 0)
        self.assertIsNotNone(area)
        self.assertEqual(area.name, "window")

    def test_locate_a_site(self):
        area = locate_area("de_mirage", -423, -2173, 0)
        self.assertIsNotNone(area)
        self.assertEqual(area.name, "a_site")

    def test_locate_b_site(self):
        area = locate_area("de_mirage", -2050, 300, 0)
        self.assertIsNotNone(area)
        self.assertEqual(area.name, "b_site")

    def test_unknown_map_returns_none(self):
        area = locate_area("de_dust2", 0, 0, 0)
        self.assertIsNone(area)

    def test_far_from_any_area_returns_none(self):
        area = locate_area("de_mirage", 5000, 5000, 0)
        self.assertIsNone(area)

    def test_point_in_area(self):
        a = AreaInfo(name="test", name_cn="测试", type="choke", center=(0.0, 0.0), radius=100.0)
        self.assertTrue(point_in_area(50, 50, a))
        self.assertFalse(point_in_area(200, 200, a))

    def test_load_map_areas_returns_list(self):
        areas = load_map_areas("de_mirage")
        self.assertIsInstance(areas, list)
        self.assertGreater(len(areas), 0)

    def test_load_nonexistent_map_returns_empty(self):
        areas = load_map_areas("de_nonexistent")
        self.assertEqual(areas, [])


if __name__ == "__main__":
    unittest.main()
