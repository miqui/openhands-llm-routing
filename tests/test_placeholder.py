import unittest


class PlaceholderTest(unittest.TestCase):
    def test_package_imports(self):
        import ohrouting

        self.assertIsNotNone(ohrouting)


if __name__ == "__main__":
    unittest.main()
