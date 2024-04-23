from ast import If
import ccxt
import time
import logging
import json
import os
import sys
import threading
import traceback
from apscheduler.schedulers.background import BackgroundScheduler
from itertools import product


# Define a function to load the configuration from the JSON file
def load_config(config_file_path):
    with open(config_file_path, "r") as config_file:
        return json.load(config_file)


# Load the configuration from the JSON file
config = load_config("config/trade_config.json")

# Set log levels based on configuration
console_log_level = getattr(logging, config["log_levels"].get("console"))
file_log_level = getattr(logging, config["log_levels"].get("file"))
ccxt_log_level = getattr(logging, config["log_levels"].get("ccxt"))
scheduler_log_level = getattr(logging, config["log_levels"].get("scheduler"))
# Configure the log
logging.basicConfig(
    filename="logs/arbitrage_bot.log",
    filemode="w",  # Overwrite the log file on startup
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Create a StreamHandler for console log
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(console_log_level)
console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)

logging.getLogger("apscheduler").setLevel(scheduler_log_level)
logging.getLogger("ccxt").setLevel(ccxt_log_level)
log = logging.getLogger()
log.setLevel(file_log_level)
log.addHandler(console_handler)
log.info("Running the arbitage bot")

# Load the bot configurations
max_retries = config["parameters"]["maxRetries"]
max_position_sizes = config.get("max_position_sizes", {})
alert_threshold = config["parameters"]["alertThreshold"]
retry_delay = config["parameters"]["retryDelay"]
min_profit_percentage = config["parameters"]["minProfitPercentage"]
slippage_threshold = config["parameters"]["slippageThreshold"]
window_size = config["parameters"]["windowSize"]
trend_threshold = config["parameters"]["trendThreshold"]
price_range_percentage = config["parameters"]["priceRangePercentage"]
min_position_reduction = config["parameters"]["minPositionReduction"]
historical_price_timeframe = config["parameters"]["historicalPriceTimeframe"]
historical_price_limit = config["parameters"]["historicalPriceLimit"]
orderbook_update_timeout = config["parameters"]["orderbookUpdateTimeout"]
opportunity_timeout = config["parameters"]["opportunityTimeout"]
process_timeout = config["parameters"]["processTimeout"]
logfile_clear_interval = config["parameters"]["logfileClearInterval"]

# Access API keys, secrets, and other parameters for all exchanges
exchanges = {}

for exchange_config in config["exchanges"]:
    exchange_name = exchange_config["name"]
    api_key = exchange_config["apiKey"]
    api_secret = exchange_config["apiSecret"]
    api_password = exchange_config["password"]

    # Use the appropriate exchange class constructor based on the exchange name
    if exchange_name == "binanceus":
        binance_key = api_key
        binance_secret = api_secret
        exchange_instance = ccxt.binanceus(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"adjustForTimeDifference": True},
            }
        )
    elif exchange_name == "kraken":
        exchange_instance = ccxt.kraken(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
        )
    elif exchange_name == "coinbasepro":
        exchange_instance = ccxt.coinbasepro(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": api_password,
                "enableRateLimit": True,
            }
        )
    elif exchange_name == "coinbase":
        exchange_instance = ccxt.coinbase(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": api_password,
                "enableRateLimit": True,
            }
        )
    exchanges[exchange_name] = exchange_instance


# Modify the clear_log_file function to truncate the log file
def clear_log_file(log_filename):
    with open(log_filename, "w"):
        pass  # Truncate the log file

    log.debug(f"Log file '{log_filename}' cleared.")


# Create a scheduler
scheduler = BackgroundScheduler()

# Schedule the clear_log_file function to run every 2 minutes
scheduler.add_job(
    clear_log_file,
    "interval",
    minutes=logfile_clear_interval,
    args=["logs/arbitrage_bot.log"],
)

# Start the scheduler
scheduler.start()


def get_adjusted_limit_price(exchange_instance, symbol):
    try:
        market_price = exchange_instance.fetch_ticker(symbol)["last"]
        new_limit_price = (
            market_price * 0.95
        )  # 95% of the current market price
        return new_limit_price
    except Exception as e:
        log.error(f"Error getting adjusted limit price: {e}")
        traceback.print_exc()
        return None


def cancel_and_adjust_orders(exchanges, max_order_age=300, interval=300):
    try:
        while True:
            log.debug("Checking and canceling open orders.")
            for exchange_name, exchange_instance in exchanges.items():
                exchange_instance.options["warnOnFetchOpenOrdersWithoutSymbol"] = False
                open_orders = exchange_instance.fetch_open_orders()
                for order in open_orders:
                    order_age = (
                        time.time() - order["timestamp"] / 1000
                    )  # Convert timestamp to seconds
                    if order_age > max_order_age:
                        log.info(
                            f"Cancelling order {order['id']} on {exchange_name} due to age."
                        )

                        # Retrieve symbol information from the order object
                        symbol = order.get("symbol")
                        if not symbol:
                            log.warning(
                                f"Symbol not found for order {order['id']} on {exchange_name}. Skipping."
                            )
                            continue

                        # Cancel the order
                        exchange_instance.cancel_order(order["id"], symbol=symbol)

                        # Review market conditions and adjust the limit price
                        new_limit_price = get_adjusted_limit_price(
                            exchange_instance, symbol
                        )
                        if new_limit_price:
                            log.info(
                                f"Adjusting limit price for order {order['id']} on {exchange_name}."
                            )

                            # Determine order side ('buy' or 'sell') and quantity ('amount')
                            order_side = "buy" if order.get("side") == "buy" else "sell"
                            order_amount = order[
                                "amount"
                            ] 

                            # Edit the limit order
                            exchange_instance.edit_limit_order(
                                order["id"],
                                symbol=symbol,
                                side=order_side,
                                amount=order_amount,
                                price=new_limit_price,
                            )

            log.debug("Finished checking and canceling open orders.")
            time.sleep(interval)
    except Exception as e:
        log.error(f"Error during order cancellation and adjustment: {e}")
        traceback.print_exc()


# start the cancellation and adjustment function in a thread:
cancel_orders_thread = threading.Thread(
    target=cancel_and_adjust_orders, args=(exchanges,)
)
cancel_orders_thread.daemon = True
cancel_orders_thread.start()


def rearrange_balances(all_trading_pairs, available_balances):
    new_available_balances = {}

    for exchange_name, trading_pairs in all_trading_pairs.items():
        exchange_balances = available_balances.get(exchange_name, {})
        rearranged_balances = {}

        for trading_pair in trading_pairs:
            for currency in trading_pair.split("/"):
                if currency in exchange_balances:
                    rearranged_balances[currency] = exchange_balances[currency]

        new_available_balances[exchange_name] = rearranged_balances

    return new_available_balances


def get_default_trading_limits(exchange_name, trading_pair):
    try:
        # Assuming "trading_limits" is a list
        trading_limits_list = config.get("trading_limits", [])

        for exchange_limits in trading_limits_list:
            exchange_limits_dict = exchange_limits.get(exchange_name, {})
            trading_pairs_limits = exchange_limits_dict.get("trading_pairs", {})

            if trading_pair in trading_pairs_limits:
                return trading_pairs_limits[trading_pair]

        log.warning(f"Trading limits not found for {exchange_name} and {trading_pair}")
        return {}

    except Exception as e:
        log.error(f"Error retrieving trading limits: {str(e)}")
        return {}


def load_markets(exchanges, reload):
    markets = {}
    for exchange_name, exchange_instance in exchanges.items():
        if reload:
            markets[exchange_name] = exchange_instance.load_markets(reload)
        else:
            markets[exchange_name] = exchange_instance.load_markets()
    log.debug("All markets loaded")
    return markets


def get_exchange_fees(exchange_symbols, markets):
    fees = {}

    for exchange_name, trading_pairs in exchange_symbols.items():
        fees[exchange_name] = {}

        for symbol in trading_pairs:
            if exchange_name in markets and symbol in markets[exchange_name]:
                symbol_info = markets[exchange_name][symbol]

                # Default fees to 0 for Binance
                if exchange_name == "binanceus":
                    buy_fee = 0
                    sell_fee = 0
                else:
                    # Use specific fees for each trading pair on other exchanges
                    buy_fee = symbol_info.get("taker", 0)
                    sell_fee = symbol_info.get("maker", 0)

                fee_info = {
                    "buy_fee": buy_fee,
                    "sell_fee": sell_fee,
                }

                fees[exchange_name][symbol] = fee_info

    log.debug(f"fees: {fees}")
    return fees


def calculate_spread_threshold(min_profit_percentage, exchange_fees, exchange_symbols):
    try:
        # Calculate the minimum spread required to achieve the desired profit
        min_profit = min_profit_percentage / 100
        log.debug(f"min profit: {min_profit}")

        # Initialize spread_thresholds dictionary
        spread_thresholds = {}

        for exchange_name, trading_pairs in exchange_symbols.items():
            if exchange_name not in exchange_fees:
                continue

            spread_thresholds[exchange_name] = {}

            for trading_pair in trading_pairs:
                fees = exchange_fees[exchange_name].get(trading_pair, {})
                maker_fee_sell = float(fees.get("sell_fee", 0))
                taker_fee_buy = float(fees.get("buy_fee", 0))

                # Calculate the spread threshold for buying
                spread_threshold_buy = (
                    min_profit * taker_fee_buy if taker_fee_buy > 0 else min_profit
                )

                # Calculate the spread threshold for selling
                spread_threshold_sell = (
                    min_profit * maker_fee_sell if maker_fee_sell > 0 else min_profit
                )

                # Log the spread thresholds for the current exchange and trading pair
                log.debug(
                    f"Spread Threshold (Buy) for {exchange_name} - {trading_pair}: {spread_threshold_buy}"
                )
                log.debug(
                    f"Spread Threshold (Sell) for {exchange_name} - {trading_pair}: {spread_threshold_sell}"
                )

                spread_thresholds[exchange_name][trading_pair] = {
                    "buy": spread_threshold_buy,
                    "sell": spread_threshold_sell,
                }

        log.debug(f"spread_thresholds: {spread_thresholds}")
        return spread_thresholds
    except Exception as e:
        log.error(f"Error calculating spread threshold: {str(e)}")
        traceback.print_exc()
        return {}


def execute_trade(exchange, order_type, symbol, price, amount):
    try:
        # Log the parameters for debugging
        base_currency, quote_currency = symbol.split("/")
        log.debug(f"base_currency: {base_currency}")
        log.debug(f"Executing trade on {exchange.id}")
        log.debug(f"Order Type: {order_type}")
        log.debug(f"Symbol: {symbol}")
        buy_order = None
        sell_order = None
        amount = exchange.currency_to_precision(base_currency, amount)
        amount = exchange.amount_to_precision(symbol, amount)

        log.debug(f"amount {amount}")
        price = exchange.price_to_precision(symbol, price)
        log.debug(f"price: {price}")

        if order_type == "buy":
            # Attempt to execute the "buy" order

            buy_order = exchange.create_limit_buy_order(symbol, amount, price)

            # Check if the "buy" order was successful
            if buy_order:
                log.info(f"Buy order executed successfully on {exchange.id}")
                return buy_order
            else:
                log.warning(f"Buy order execution failed on {exchange.id}")
                return None
        elif order_type == "sell":
            # Attempt to execute the "sell" order
            sell_order = exchange.create_limit_sell_order(symbol, amount, price)

            # Check if the "sell" order was successful
            if sell_order:
                log.info(f"Sell order executed successfully on {exchange.id}")
                return sell_order
            else:
                log.warning(f"Sell order execution failed on {exchange.id}")
                return None
        else:
            log.warning(f"Invalid order type: {order_type}")
            return None
    except Exception as e:
        log.error(f"Order execution error on {exchange.id}: {str(e)}")
        traceback.print_exc()


def fetch_historical_prices(exchange, symbol, timeframe, limit):
    try:
        historical_prices = exchange.fetch_ohlcv(symbol, timeframe, limit)
        return historical_prices
    except Exception as e:
        log.error(f"Error fetching historical prices for {symbol}: {str(e)}")
        return None


def analyze_trend(historical_prices):
    if len(historical_prices) >= window_size:
        prices = [
            price[4] for price in historical_prices[-window_size:]
        ]  # Adjust the index based on the structure of your OHLCV data

        # Calculate the simple moving average
        sma = sum(prices) / window_size

        # Compare the last price with the moving average
        last_price = prices[-1]

        # Calculate the percentage change from the first to the last price
        price_change_percentage = ((last_price - sma) / sma) * 100

        log.debug(f"Last Price: {last_price}")
        log.debug(f"Simple Moving Average: {sma}")
        log.debug(f"Price Change Percentage: {price_change_percentage}")

        if price_change_percentage > trend_threshold:
            log.debug("Trend: up")
            return "up"
        elif price_change_percentage < -trend_threshold:
            log.debug("Trend: down")
            return "down"
        else:
            log.debug("Trend: stable")
            return "stable"
    else:
        return "unknown"


def get_exchange_rate(exchange, symbol):
    return exchange.fetch_ticker(symbol)["last"]


def advanced_arbitrage_strategy(
    symbol,
    spread_thresholds,
    exchange_symbols,
    exchange_fees,
    max_position_sizes,
):
    opportunities = {}

    try:
        log.debug(f"Searching for opportunities in {symbol} on all exchanges")
        # clear_log_file("arbitrage_bot.log", max_age_minutes=2)
        available_balances = fetch_available_balances(exchanges)
        available_balances = rearrange_balances(exchange_symbols, available_balances)
        exchange_names = list(exchange_symbols.keys())

        # Iterate through all combinations of exchange pairs
        for exchange_i, exchange_j in product(exchange_names, repeat=2):
            # Skip pairs where the same exchange is selected
            if exchange_i == exchange_j:
                continue

            exchange_i_default_limits = get_default_trading_limits(exchange_i, symbol)
            exchange_j_default_limits = get_default_trading_limits(exchange_j, symbol)

            base_currency, quote_currency = symbol.split("/")
            symbol_info_i = exchanges[exchange_i].markets[symbol]
            symbol_info_j = exchanges[exchange_j].markets[symbol]

            min_amount_i = symbol_info_i["limits"]["amount"].get(
                "min", exchange_i_default_limits.get("minimum_amount")
            )
            min_amount_j = symbol_info_j["limits"]["amount"].get(
                "min", exchange_j_default_limits.get("minimum_amount")
            )

            min_cost_i = symbol_info_i["limits"]["cost"].get("min", 0)
            min_cost_j = symbol_info_j["limits"]["cost"].get("min", 0)
            if min_cost_i is None:
                min_cost_i = 0
            if min_cost_j is None:
                min_cost_j = 0

            if exchange_i == "binanceus":
                min_amount_i = exchange_i_default_limits.get("minimum_amount")

            if exchange_i == "binanceus":
                min_amount_j = exchange_j_default_limits.get("minimum_amount")

            # Fetch the latest market prices for the symbol on each exchange
            last_price_i = get_exchange_rate(exchanges[exchange_i], symbol)
            last_price_j = get_exchange_rate(exchanges[exchange_j], symbol)
            balance_i = available_balances.get(exchange_i, {})
            balance_j = available_balances.get(exchange_j, {})

            buy_quote_balance = float(balance_i.get(quote_currency, 0))
            buy_fee = (
                exchange_fees.get(exchange_i, {}).get(symbol, {}).get("buy_fee", 0.0)
            )
            effective_buy_fee = (1.0 - (buy_fee / 100)) + min_position_reduction

            max_buyable_base_i = buy_quote_balance / (last_price_i * effective_buy_fee)

            if max_buyable_base_i < min_amount_i:
                log.debug(
                    f"Calculated position size for {exchange_i} does not meet the minimum trade size for buy. Minimum Amount: {min_amount_i} Trading Pair: {symbol}"
                )
                continue

            sell_base_balance = float(balance_j.get(base_currency, 0))

            if sell_base_balance < min_amount_j:
                log.debug(
                    f"Available balance for {exchange_j} does not meet the minimum trade size for sell. Minimum Amount: {min_amount_j} Trading Pair: {symbol}"
                )
                continue

            # Check if the symbol is available on both exchanges
            if (
                symbol in exchange_symbols[exchange_i]
                and symbol in exchange_symbols[exchange_j]
            ):
                # Check if the order_books exist for both exchanges
                if exchange_i in all_order_books and exchange_j in all_order_books:
                    order_book_i = all_order_books[exchange_i].get(symbol, {})
                    order_book_j = all_order_books[exchange_j].get(symbol, {})

                    historical_prices_i = fetch_historical_prices(
                        exchanges[exchange_i],
                        symbol,
                        historical_price_timeframe,
                        historical_price_limit,
                    )
                    historical_prices_j = fetch_historical_prices(
                        exchanges[exchange_j],
                        symbol,
                        historical_price_timeframe,
                        historical_price_limit,
                    )

                    # Ensure historical prices are available
                    if historical_prices_i is None or historical_prices_j is None:
                        log.debug(
                            f"Unable to fetch historical prices for {symbol} on {exchange_i} or {exchange_j}"
                        )
                        continue

                    # analyze the trend based on historical prices
                    trend_direction_i = analyze_trend(historical_prices_i)
                    trend_direction_j = analyze_trend(historical_prices_j)

                    # Iterate through all items in the order book
                    for bid_i in order_book_i.get("bids", []):
                        for ask_j in order_book_j.get("asks", []):
                            bid_price_i = bid_i[0]
                            ask_price_j = ask_j[0]

                            if last_price_i * (
                                1.0 - price_range_percentage / 100
                            ) <= bid_price_i <= last_price_i * (
                                1.0 + price_range_percentage / 100
                            ) and last_price_j * (
                                1.0 - price_range_percentage / 100
                            ) <= ask_price_j <= last_price_j * (
                                1.0 + price_range_percentage / 100
                            ):
                                spread_percentage = (
                                    (ask_price_j - bid_price_i) / bid_price_i
                                ) * 100

                                # Extract the spread thresholds for buying and selling based on the exchange
                                spread_threshold_i = spread_thresholds.get(
                                    exchange_i, {}
                                ).get(symbol, {"buy": 0, "sell": 0})
                                spread_threshold_j = spread_thresholds.get(
                                    exchange_j, {}
                                ).get(symbol, {"buy": 0, "sell": 0})

                                # Consider trend direction in the decision-making process
                                if (
                                    spread_percentage > spread_threshold_i["buy"]
                                    and spread_percentage > spread_threshold_j["sell"]
                                    and trend_direction_i == "down"
                                    and trend_direction_j == "up"
                                    or spread_percentage > spread_threshold_i["buy"]
                                    and spread_percentage > spread_threshold_j["sell"]
                                    and trend_direction_i == "stable"
                                    and trend_direction_j == "stable"
                                    or spread_percentage > spread_threshold_i["buy"]
                                    and spread_percentage > spread_threshold_j["sell"]
                                    and trend_direction_i == "down"
                                    and trend_direction_j == "stable"
                                ):
                                    # Calculate the maximum position size for buying
                                    max_position_size_base_i = min(
                                        max_buyable_base_i,
                                        max_position_sizes.get(base_currency),
                                    )

                                    # Calculate the maximum position size for selling
                                    max_position_size_base_j = min(
                                        sell_base_balance, max_position_size_base_i
                                    )

                                    if (
                                        max_position_size_base_i * bid_price_i
                                    ) >= min_cost_i and (
                                        max_position_size_base_j * ask_price_j
                                    ) >= min_cost_j:
                                        # Ensure positions are equal
                                        max_position_size_base_i = min(
                                            max_position_size_base_i,
                                            max_position_size_base_j,
                                        )
                                        max_position_size_base_j = (
                                            max_position_size_base_i
                                        )

                                        log.debug(
                                            f"max_position_size_base_i: {max_position_size_base_i:.8f}"
                                        )
                                        log.debug(
                                            f"max_position_size_base_j: {max_position_size_base_j:.8f}"
                                        )
                                        log.debug(
                                            f"Final Position Size for {symbol} on {exchange_i}: {max_position_size_base_i:.8f}"
                                        )
                                        log.debug(
                                            f"Final Position Size for {symbol} on {exchange_j}: {max_position_size_base_j:.8f}"
                                        )
                                        # Calculate the actual amount used for buying
                                        amount_used_for_buy = (
                                            max_position_size_base_i * bid_price_i
                                        )

                                        # Calculate the actual amount received from selling
                                        amount_received_from_sell = (
                                            max_position_size_base_j * ask_price_j
                                        )

                                        # Calculate the profit based on the actual amounts
                                        profit = (
                                            amount_received_from_sell
                                            - amount_used_for_buy
                                        )

                                        log.debug(
                                            f"Profit: {profit:.8f} {quote_currency} Exchange A: {exchange_i} - Exchange B: {exchange_j}"
                                        )

                                        opportunities[symbol] = {
                                            "bid_price": bid_price_i,
                                            "ask_price": ask_price_j,
                                            "max_position_size_base_i": max_position_size_base_i,
                                            "max_position_size_base_j": max_position_size_base_j,
                                            "exchange_i": exchange_i,
                                            "exchange_j": exchange_j,
                                        }
                                        log.debug(f"Symbol: {symbol}")
                                        log.debug(f"Spread: {spread_percentage}")
                                        log.debug(
                                            f"Trend Direction A: {trend_direction_i} - Trend Direction B: {trend_direction_j}"
                                        )
                                        log.debug(
                                            f"{exchange_i} Bid Price: {bid_price_i}"
                                        )
                                        log.debug(
                                            f"{exchange_j} Ask Price: {ask_price_j}"
                                        )

                                        # exit the loop after an opportunity is found
                                        break
                                    else:
                                        log.debug("Cost not met for buy or sell")
                                else:
                                    log.debug(
                                        f"Spread threshold not met or trend direction is not favorable. Spread Percentage: {spread_percentage}, Trend Direction A: {trend_direction_i}, Trend Direction B: {trend_direction_j}"
                                    )

                    # exit the outer loop after an opportunity is found
                    if "opportunities" in locals() and opportunities:
                        break
    except Exception as e:
        log.error(f"Error in advanced_arbitrage_strategy: {str(e)}")
        traceback.print_exc()
    return opportunities


def fetch_trading_pairs(exchanges, available_balances, markets):
    all_trading_pairs = {}

    # Create a set of all unique currencies across all exchanges
    all_unique_currencies = set()

    for exchange_name, exchange_instance in exchanges.items():
        try:
            trading_pairs = set()

            # Get available balances for the exchange
            exchange_balances = available_balances.get(exchange_name, {})

            # Create a set of unique currencies with non-zero balances for this exchange
            unique_currencies = {
                currency
                for currency, balance in exchange_balances.items()
                if float(balance) > 0
            }

            # Log the available balances and unique currencies for debugging
            log.debug(f"available_balances for {exchange_name}: {exchange_balances}")
            log.debug(
                f"Unique currencies for {exchange_name}: {list(unique_currencies)}"
            )

            # Add the unique currencies of this exchange to the all_unique_currencies set
            all_unique_currencies.update(unique_currencies)

            # Iterate through the markets and check if trading pairs can be formed
            for symbol, symbol_info in markets[exchange_name].items():
                if symbol_info["active"]:
                    base_currency, quote_currency = symbol.split("/")

                    # Check if both base and quote currencies exist in unique_currencies
                    if (
                        base_currency in unique_currencies
                        and quote_currency in unique_currencies
                    ):
                        trading_pairs.add(symbol)

            # Log the trading pairs for debugging
            log.debug(f"Trading pairs for {exchange_name}: {list(trading_pairs)}")
            all_trading_pairs[exchange_name] = list(trading_pairs)

        except Exception as e:
            log.error(f"Error fetching trading pairs for {exchange_name}: {str(e)}")

    # Add all possible trading pairs to exchanges if they are in the market
    for exchange_name, exchange_instance in exchanges.items():
        existing_trading_pairs = set(all_trading_pairs.get(exchange_name, []))
        all_possible_trading_pairs = set()

        for base_currency in all_unique_currencies:
            for quote_currency in all_unique_currencies:
                if base_currency != quote_currency:
                    trading_pair = f"{base_currency}/{quote_currency}"

                    # Check if the trading pair is in the market for the exchange
                    if trading_pair in markets[exchange_name]:
                        # Check if the trading pair is not already in the trading pairs for the exchange
                        if trading_pair not in existing_trading_pairs:
                            all_possible_trading_pairs.add(trading_pair)

        # Add the new trading pairs to the existing ones
        all_trading_pairs[exchange_name].extend(list(all_possible_trading_pairs))

    available_balances = rearrange_balances(all_trading_pairs, exchange_balances)
    log.info(f"all_trading_pairs: {all_trading_pairs}")
    return all_trading_pairs


# Fetch available balances for each exchange
def fetch_available_balances(exchanges):
    available_balances = {}

    for exchange_name, exchange_instance in exchanges.items():
        retry_count = 0
        while retry_count < max_retries:
            try:
                balance = exchange_instance.fetch_balance()
                non_empty_balances = {
                    currency: float(amount)
                    for currency, amount in balance["free"].items()
                    if float(amount) > 0
                }
                available_balances[exchange_name] = non_empty_balances
                break  # Exit the retry loop if successful
            except Exception as e:
                log.error(
                    f"Attempt {retry_count + 1} - Error fetching available balance for {exchange_name}: {str(e)}"
                )
                retry_count += 1
                if retry_count < max_retries:
                    log.debug(
                        f"Retrying to fetch balance for {exchange_name} after {retry_delay} seconds..."
                    )
                    time.sleep(retry_delay)
                else:
                    log.error(
                        f"Failed to fetch balance for {exchange_name} after {max_retries} attempts."
                    )
    return available_balances


available_balances = fetch_available_balances(exchanges)

# Initialize exchange_symbols dictionary
exchange_symbols = {}

markets = load_markets(exchanges, False)


# Fetch trading pairs for each exchange and populate the exchange_symbols dictionary
exchange_symbols = fetch_trading_pairs(exchanges, available_balances, markets)

# Get exchange fees
exchange_fees = get_exchange_fees(exchange_symbols, markets)


# Collect all order books in a dictionary
all_order_books = {}

# Calculate the spread threshold based on the minimum profit percentage and exchange fees
spread_threshold = calculate_spread_threshold(
    min_profit_percentage, exchange_fees, exchange_symbols
)


# Function to periodically update order books
def update_order_books():
    while True:
        try:
            for exchange_name, symbols in exchange_symbols.items():
                order_books = {}
                for symbol in symbols:
                    order_book = exchanges[exchange_name].fetch_order_book(symbol)
                    order_books[symbol] = order_book
                all_order_books[exchange_name] = order_books
            time.sleep(orderbook_update_timeout)  # Update order books every minute
        except Exception as e:
            log.error(f"Error updating order books: {str(e)}")
            traceback.print_exc()


# Start the order book update thread
order_book_thread = threading.Thread(target=update_order_books)
order_book_thread.daemon = True
order_book_thread.start()
order_books = {exchange_name: {} for exchange_name in exchange_symbols}

# Main loop
while True:
    try:
        for exchange_name, symbols in exchange_symbols.items():
            for symbol in symbols:
                time.sleep(opportunity_timeout)
                opportunities = advanced_arbitrage_strategy(
                    symbol,
                    spread_threshold,
                    exchange_symbols,
                    exchange_fees,
                    max_position_sizes,
                )
                if opportunities:
                    selected_opportunity = opportunities.get(symbol)
                    bid_price = selected_opportunity["bid_price"]
                    ask_price = selected_opportunity["ask_price"]
                    position_size_i = selected_opportunity["max_position_size_base_i"]
                    position_size_j = selected_opportunity["max_position_size_base_j"]
                    exchange_i = selected_opportunity["exchange_i"]
                    exchange_j = selected_opportunity["exchange_j"]
                    exchange_i_instance = exchanges[exchange_i]
                    exchange_j_instance = exchanges[exchange_j]
                    quote_currency = symbol.split("/")[1]

                    # Check if there is sufficient balance to execute the trade
                    log.debug(f"position size: {position_size_i}")

                    # Calculate expected execution prices based on bid and ask prices
                    expected_buy_price = bid_price
                    expected_sell_price = ask_price

                    # Get the current market prices
                    current_buy_prices = all_order_books[exchange_i][symbol]["bids"]
                    current_sell_prices = all_order_books[exchange_j][symbol]["asks"]

                    # Initialize variables to store selected bid and ask prices
                    selected_buy_price = None
                    selected_sell_price = None

                    # Iterate through bid prices until finding one that meets criteria
                    for bid in current_buy_prices:
                        current_buy_price = bid[0]
                        slippage_buy = (
                            (current_buy_price - expected_buy_price)
                            / expected_buy_price
                        ) * 100

                        # Check if slippage is within the threshold
                        if abs(slippage_buy) <= slippage_threshold:
                            selected_buy_price = current_buy_price
                            break

                    # Iterate through ask prices until finding one that meets criteria
                    for ask in current_sell_prices:
                        current_sell_price = ask[0]
                        slippage_sell = (
                            (expected_sell_price - current_sell_price)
                            / expected_sell_price
                        ) * 100

                        # Check if slippage is within the threshold
                        if abs(slippage_sell) <= slippage_threshold:
                            selected_sell_price = current_sell_price
                            break

                    # Check if both selected buy and sell prices are found
                    if (
                        selected_buy_price is not None
                        and selected_sell_price is not None
                    ):
                        # Execute buy and sell orders using selected prices
                        buy_order = execute_trade(
                            exchange_i_instance,
                            "buy",
                            symbol,
                            selected_buy_price,
                            position_size_i,
                        )
                        if buy_order:
                            sell_order = execute_trade(
                                exchange_j_instance,
                                "sell",
                                symbol,
                                selected_sell_price,
                                position_size_j,
                            )

                            # Calculate profit in USD
                            profit = (
                                position_size_j * ask_price
                                - position_size_i * selected_buy_price
                            )
                            base_currency, quote_currency = symbol.split("/")
                            profit_in_usd = profit * get_exchange_rate(
                                exchange_i_instance, f"{quote_currency}/USD"
                            )

                            log.info(
                                f"Profit in USD: {profit_in_usd:.8f} Exchange A: {exchange_i} - Exchange B: {exchange_j}"
                            )
                        else:
                            log.warning(
                                "Skipping 'sell' order due to unsuccessful 'buy' order."
                            )
                    else:
                        log.warning(
                            "No suitable prices found within the slippage threshold."
                        )

                    # break after executing one trade
                    break
            time.sleep(process_timeout)
            markets = load_markets(exchanges, True)
    except Exception as e:
        log.error(f"Error in main trading loop: {str(e)}")
        traceback.print_exc()
