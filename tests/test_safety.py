import unittest

from client import PolymarketClient


class SafetyTests(unittest.TestCase):
    def test_round_price_down_to_tick(self):
        self.assertEqual(PolymarketClient.round_price(0.537, 0.01), 0.53)
        self.assertEqual(PolymarketClient.round_price(0.537, 0.005), 0.535)

    def test_round_price_bounds(self):
        self.assertEqual(PolymarketClient.round_price(0.001, 0.01), 0.01)
        self.assertEqual(PolymarketClient.round_price(1.2, 0.01), 0.99)

    def test_invalid_book_rejected(self):
        client = object.__new__(PolymarketClient)
        client.dry_run = True
        client.market_rules = {}
        client._last_rules_refresh = {}
        client.get_order_book = lambda token: {"bids": [{"price": "0.60"}], "asks": [{"price": "0.50"}]}
        with self.assertRaises(RuntimeError):
            client.quote_from_book("x")

    def test_one_sided_book_rejected(self):
        client = object.__new__(PolymarketClient)
        client.dry_run = True
        client.market_rules = {}
        client._last_rules_refresh = {}
        client.get_order_book = lambda token: {"bids": [], "asks": [{"price": "0.50"}]}
        with self.assertRaises(RuntimeError):
            client.quote_from_book("x")


if __name__ == "__main__":
    unittest.main()
