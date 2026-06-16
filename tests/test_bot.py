import unittest
import asyncio
from config import Config
from client import PolymarketClient
from bot import VolumeBot

class TestPolymarketBot(unittest.TestCase):
    def setUp(self):
        # Set configuration for testing
        Config.DRY_RUN = True
        Config.STRATEGY = "market_making"
        Config.ORDER_SIZE = 5.0
        Config.SPREAD = 0.02
        Config.MAX_POSITION = 50.0
        Config.POLL_INTERVAL = 1
        
    def test_config_validation(self):
        """Test configuration validation."""
        Config.validate()
        
        # Test invalid strategy
        Config.STRATEGY = "invalid_strategy"
        with self.assertRaises(ValueError):
            Config.validate()
        Config.STRATEGY = "market_making"
        
        # Test negative order size
        Config.ORDER_SIZE = -10
        with self.assertRaises(ValueError):
            Config.validate()
        Config.ORDER_SIZE = 5.0

    def test_client_dry_run(self):
        """Test client mock behavior under dry-run."""
        client = PolymarketClient()
        self.assertTrue(client.dry_run)
        
        # Fetch markets (should return mock list)
        markets = client.fetch_world_cup_markets()
        self.assertTrue(len(markets) > 0)
        self.assertIn("question", markets[0])
        self.assertIn("yes_token", markets[0])
        self.assertIn("no_token", markets[0])
        
        # Get midpoint
        midpoint = client.get_midpoint_price(markets[0]["yes_token"])
        self.assertTrue(0.0 <= midpoint <= 1.0)
        
        # Place order
        resp = client.place_limit_order(markets[0]["yes_token"], 0.50, 10, "buy")
        self.assertEqual(resp["status"], "SUCCESS")

    def test_bot_cycle(self):
        """Test a single bot polling cycle in simulation mode."""
        bot = VolumeBot()
        self.assertEqual(bot.strategy, "market_making")
        
        # We run a simple check to verify that we can execute the market making loop without exceptions
        markets = bot.client.fetch_world_cup_markets()
        self.assertTrue(len(markets) > 0)
        
        # Run market making on the first mock market
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(bot._run_market_making(markets[0]))
            success = True
        except Exception as e:
            print("Error running market making:", e)
            success = False
            
        self.assertTrue(success)

    def test_bot_offset_cycle(self):
        """Test a single bot offset cycle in simulation mode."""
        bot = VolumeBot()
        bot.strategy = "yes_no_offset"
        
        markets = bot.client.fetch_world_cup_markets()
        self.assertTrue(len(markets) > 0)
        
        # Run offsetting strategy
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(bot._run_yes_no_offset(markets[0]))
            success = True
        except Exception as e:
            print("Error running offset strategy:", e)
            success = False
            
        self.assertTrue(success)

if __name__ == '__main__':
    unittest.main()
