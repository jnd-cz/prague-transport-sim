"""Deliberately failing (#222: CI must go red); reverted in the next commit."""
import unittest


class Fails(unittest.TestCase):
    def test_ci_reports_a_failure(self):
        self.assertEqual(1, 2)


if __name__ == "__main__":
    unittest.main()
