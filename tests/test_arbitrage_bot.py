import unittest
from unittest.mock import mock_open, patch, Mock
from scripts.arbitrage_bot import (
    load_config,
    clear_log_file,
    get_adjusted_limit_price,
    configure_logging,
    execute_trade,
    fetch_available_balances,
    fetch_trading_pairs,
    analyze_trend,
    update_order_books,
    calculate_spread_threshold,
)


class TestArbitrageBot(unittest.TestCase):

    @patch("builtins.open", new_callable=mock_open, read_data='{"key": "value"}')
    def test_load_config_success(self, mock_file):
        result = load_config("config/trade_config.json")
        self.assertEqual(result, {"key": "value"})

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_load_config_file_not_found(self, mock_file):
        with self.assertRaises(FileNotFoundError):
            load_config("config/trade_config.json")

    @patch("builtins.open", new_callable=mock_open)
    @patch("scripts.arbitrage_bot.logging.debug")
    def test_clear_log_file(self, mock_log, mock_file):
        clear_log_file("logs/arbitrage_bot.log")
        mock_file.assert_called_once_with("logs/arbitrage_bot.log", "w")
        mock_log.assert_called_with("Log file 'logs/arbitrage_bot.log' cleared.")

    @patch("scripts.arbitrage_bot.logging.error")
    def test_get_adjusted_limit_price_success(self, mock_log):
        mock_exchange = Mock()
        mock_exchange.fetch_ticker.return_value = {"last": 200}
        result = get_adjusted_limit_price(mock_exchange, "BTC/USD")
        self.assertEqual(result, 190)

    @patch("scripts.arbitrage_bot.logging.error")
    def test_get_adjusted_limit_price_failure(self, mock_log):
        mock_exchange = Mock()
        mock_exchange.fetch_ticker.side_effect = Exception("API error")
        result = get_adjusted_limit_price(mock_exchange, "BTC/USD")
        mock_log.assert_called_with("Error getting adjusted limit price: API error")
        self.assertIsNone(result)

    @patch("scripts.arbitrage_bot.logging.basicConfig")
    @patch("scripts.arbitrage_bot.logging.getLogger")
    @patch("scripts.arbitrage_bot.logging.StreamHandler")
    def test_configure_logging(
        self, mock_stream_handler, mock_get_logger, mock_basic_config
    ):
        config = {"log_levels": {"console": "DEBUG", "file": "INFO"}}
        configure_logging(config)
        mock_basic_config.assert_called_once()
        mock_get_logger.assert_called()
        mock_stream_handler.assert_called()

    @patch("scripts.arbitrage_bot.ccxt.binance")
    def test_execute_trade(self, mock_exchange):
        mock_exchange.create_limit_buy_order.return_value = {
            "id": "12345",
            "status": "open",
        }
        result = execute_trade(mock_exchange, "buy", "BTC/USD", 10000, 1)
        mock_exchange.create_limit_buy_order.assert_called_with("BTC/USD", 1, 10000)
        self.assertEqual(result, {"id": "12345", "status": "open"})

    @patch("scripts.arbitrage_bot.ccxt.kraken")
    def test_fetch_available_balances(self, mock_exchange):
        mock_exchange.fetch_balance.return_value = {"free": {"BTC": 0.5, "USD": 1000}}
        balances = fetch_available_balances(mock_exchange)
        mock_exchange.fetch_balance.assert_called_once()
        self.assertEqual(balances, {"BTC": 0.5, "USD": 1000})

    @patch("scripts.arbitrage_bot.ccxt.coinbasepro")
    def test_fetch_trading_pairs(self, mock_exchange):
        mock_exchange.load_markets.return_value = {
            "BTC/USD": {"active": True},
            "ETH/USD": {"active": True},
        }
        trading_pairs = fetch_trading_pairs(mock_exchange)
        mock_exchange.load_markets.assert_called_once()
        self.assertIn("BTC/USD", trading_pairs)
        self.assertIn("ETH/USD", trading_pairs)

    def test_analyze_trend(self):
        historical_prices = [100, 105, 110, 115, 120]
        trend = analyze_trend(historical_prices)
        self.assertEqual(trend, "up")

    @patch("scripts.arbitrage_bot.ccxt.kraken")
    def test_update_order_books(self, mock_exchange):
        mock_exchange.fetch_order_book.return_value = {
            "bids": [(100, 1)],
            "asks": [(102, 1)],
        }
        order_books = update_order_books(mock_exchange, ["BTC/USD"])
        self.assertIn("BTC/USD", order_books)
        self.assertEqual(
            order_books["BTC/USD"], {"bids": [(100, 1)], "asks": [(102, 1)]}
        )

    def test_calculate_spread_threshold(self):
        fees = {"buy_fee": 0.1, "sell_fee": 0.1}
        min_profit_percentage = 1
        thresholds = calculate_spread_threshold(fees, min_profit_percentage)
        self.assertGreater(thresholds["buy"], 0)
        self.assertGreater(thresholds["sell"], 0)


if __name__ == "__main__":
    unittest.main()
