# Arbitrage Bot

## Description

This Arbitrage Bot is designed to exploit price discrepancies between different cryptocurrency centralized
 exchanges automatically. It continuously monitors and compares prices across multiple platforms and executes trades to capitalize on arbitrage opportunities. The bot utilizes `ccxt` for interacting with various exchanges, schedules tasks with `apscheduler`, and manages its own logging and error handling.

## Features

- Supports multiple exchanges including Binance US, Kraken, and Coinbase Pro.
- Configurable trading parameters and logging levels through JSON files.
- Scheduled tasks for log file maintenance and routine checks.
- Error handling and recovery mechanisms for robust operation.

## Dependencies

To run this bot, you will need Python 3.x and the following Python packages:

- `ccxt` for exchange integration.
- `apscheduler` for job scheduling.
- `logging` for output logging.
- Additional standard libraries: `json`, `os`, `sys`, `threading`, `time`, `traceback`.

## Configuration

Configuration parameters such as API keys, log levels, and trading parameters should be defined in `trade_config.json`. Here is an example structure of the config file:

```json
{
  "exchanges": [
    {
      "name": "binanceus",
      "apiKey": "your_api_key",
      "secret": "your_secret",
      "password": "{optional_api_password}"
    },
    {
      "name": "{exchange2_name}",
      "apiKey": "{api_key}",
      "secret": "{api_secret}",
      "password": "{optional_api_password}"
    }
  ],
  "log_levels": {
    "console": "DEBUG",
    "file": "ERROR",
    "ccxt": "INFO",
    "scheduler": "WARNING"
  },
  "parameters": {
        "maxRetries": 3,
        "alertThreshold": 10000.0,
        "retryDelay": 5,
        "minProfitPercentage": 50.0,
        "slippageThreshold": 0,
        "windowSize": 15,
        "trendThreshold": 0.5,
        "priceRangePercentage": 2,
        "minPositionReduction": 0.01, 
        "historicalPriceTimeframe": "1m",
        "historicalPriceLimit": 100,
        "orderbookUpdateTimeout": 5,
        "opportunityTimeout": 1,
        "processTimeout": 5,
        "logfileClearInterval": 5
    },
  "max_position_sizes": {
        "BTC": 0.0002,
        "ETH": 0.004,
        "USDT": 10.0
    },
      "trading_limits": [ 
      {
      "binanceus": {
          "trading_pairs": {
              "BTC/USDT": {
                  "minimum_amount": 0.0001,
                  "minimum_order_size" : 0.00003
              },
              "ETH/USDT": {
                  "minimum_amount": 	0.00001,
                  "minimum_order_size" : 1
              },
              "ETH/BTC": {
                  "minimum_amount": 	0.00001,
                  "minimum_order_size" : 1
              }
          }
      },
      "coinbasepro": {
          "trading_pairs": {
              "BTC/USDT": {
                  "minimum_amount": 0.0003,
                  "minimum_order_size" : 1
              },
              "ETH/USDT": {
                  "minimum_amount": 	0.00002,
                  "minimum_order_size" : 0.01
              },
              "ETH/BTC": {
                  "minimum_amount": 	0.00002,
                  "minimum_order_size" : 0.01
              }
              }
          }
      }
      ]
}
```

## Setup Instructions

1. Clone this repository to your local machine.
2. Install required Python packages:

```bash
pip install ccxt apscheduler
```

3. Configure the trade_config.json with your specific parameters.
4. Start the bot by running the script:

```bash
python arbitrage_bot.py
```

## Logging

Logs are written to logs/arbitrage_bot.log with detailed information about operations and encountered issues. The log file is configured to be cleared at a set interval to prevent uncontrolled growth.

## Disclaimer

This bot is for educational and development purposes only.
