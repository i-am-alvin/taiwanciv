"""Population growth from year-end registered population (pipeline/build/growth.py)."""

import unittest

from pipeline.build.growth import Growth, rate

RIS = {
    "years": [2020, 2021, 2022, 2023, 2024, 2025],
    "nation": [100, 100, 101, 102, 103, 104],
    "counties": {"63000": [50, 50, 49, 48, 47, 45], "09007": [10, None, 11, 11, 12, 12], "10016": [1, 1, 1, 1, 1, 2]},
}


class GrowthTest(unittest.TestCase):
    def test_window_is_2021_to_latest(self):
        g = Growth(RIS)
        self.assertEqual(g.years, [2021, 2025])
        self.assertEqual(g.nation(), 0.04)
        self.assertEqual(g.county("63000"), -0.1)

    def test_null_never_guessed(self):
        g = Growth(RIS)
        self.assertIsNone(g.county("09007"))  # 2021 missing
        self.assertIsNone(g.county("10016"))  # +100% is beyond the sanity cap
        self.assertIsNone(g.county("99999"))
        self.assertIsNone(rate(None, 5))

    def test_series_and_population(self):
        g = Growth(RIS)
        self.assertEqual(g.series(RIS["counties"]["63000"])["2025"], 45)
        self.assertEqual(g.population("63000"), 45)
        self.assertEqual(g.population(), 104)
