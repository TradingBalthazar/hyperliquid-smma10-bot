# Hyperliquid Trading Bot

This repository contains trading bots for Hyperliquid that use different moving average strategies.

## Available Strategies

### 1. SMMA-10 Slope Strategy (v5)

This strategy:
1. Uses a 10-period SMMA (Smoothed Moving Average)
2. Places aggressive buy orders when SMMA slope turns positive
3. Places aggressive sell orders when SMMA slope turns negative
4. Uses reduce-only orders when there are existing positions in the opposite direction
5. Uses limit orders only
6. Ensures minimum order value is $10 to prevent order failures
7. Improved reduce-only logic to only close positions when slope changes
8. Added position management for low margin situations (without closing positions)

### 2. ALMA Slope Strategy (v1)

This strategy:
1. Uses the Arnaud Legoux Moving Average (ALMA)
2. Places aggressive buy orders when ALMA slope turns positive
3. Places aggressive sell orders when ALMA slope turns negative
4. Uses reduce-only orders to close 100% of existing positions when slope is opposite to position
5. Uses limit orders with pricing set for immediate execution
6. Ensures minimum order value is $10 to prevent order failures
7. Improved reduce-only logic to close positions when slope is opposite to position
8. Added position management for low margin situations (without closing positions)

#### About ALMA

The Arnaud Legoux Moving Average (ALMA) is a technical indicator designed by Arnaud Legoux and Dimitris Kouzis-Loukas in 2009. It uses a Gaussian distribution function to calculate a weighted average of an asset's price, reducing lag and noise compared to traditional moving averages.

Key parameters:
- Window Size: Default 9 periods
- Offset: Default 0.85 (controls the Gaussian peak position)
- Sigma: Default 6 (controls the Gaussian curve width)

ALMA provides a smoother curve with reduced lag compared to traditional moving averages like SMA, EMA, and SMMA.

## Deployment on Railway

### Option 1: Deploy from GitHub

1. Fork this repository
2. Go to [Railway](https://railway.app/)
3. Create a new project
4. Select "Deploy from GitHub"
5. Connect to your GitHub account and select this repository
6. Set the following environment variables:
   - `PRIVATE_KEY`: Your Hyperliquid private key
   - `WALLET_ADDRESS`: Your Hyperliquid wallet address
   - `SYMBOL`: The trading pair (default: "HYPE/USDC:USDC")
   - `COIN`: The coin symbol (default: "HYPE")
   - `LEVERAGE`: The leverage to use (default: 3)
7. Deploy the project

### Option 2: Deploy from CLI

1. Install the Railway CLI: `curl -fsSL https://railway.app/install.sh | sh`
2. Login to Railway: `railway login`
3. Clone this repository: `git clone https://github.com/TradingBalthazar/hyperliquid-smma10-bot.git`
4. Navigate to the repository: `cd hyperliquid-smma10-bot`
5. Create a new project: `railway init`
6. Set the environment variables:
   ```
   railway variables --set "PRIVATE_KEY=your_private_key_here" \
                     --set "WALLET_ADDRESS=your_wallet_address_here" \
                     --set "SYMBOL=HYPE/USDC:USDC" \
                     --set "COIN=HYPE" \
                     --set "LEVERAGE=3"
   ```
7. Deploy the project: `railway up`

## Configuration

You can configure the strategies by setting the following environment variables:

### Common Parameters

- `PRIVATE_KEY`: Your Hyperliquid private key
- `WALLET_ADDRESS`: Your Hyperliquid wallet address
- `SYMBOL`: The trading pair (default: "HYPE/USDC:USDC")
- `COIN`: The coin symbol (default: "HYPE")
- `TIMEFRAME`: The timeframe for candles (default: "1m")
- `LOOKBACK_PERIODS`: Number of periods to look back (default: 20)
- `LEVERAGE`: The leverage to use (default: 3)
- `SLOPE_LOOKBACK`: Number of periods to calculate slope (default: 2)
- `BASE_ORDER_SIZE`: Base size in tokens (default: 0.65)
- `LEVEL_SPACING_PERCENT`: Spacing between levels (default: 0.0005)
- `NUM_LEVELS`: Number of order levels (default: 5)
- `ORDER_REFRESH_SECONDS`: How often to refresh orders (default: 10)
- `MIN_ORDER_SIZE`: Minimum order size (default: 0.1)
- `MIN_ORDER_VALUE`: Minimum order value in USDC (default: 10)
- `MARGIN_SAFETY_FACTOR`: Margin safety factor (default: 0.7)
- `POSITION_CHECK_INTERVAL`: Check positions every X seconds (default: 5)

### SMMA Strategy Parameters

- `SMMA_PERIOD`: The period for SMMA calculation (default: 10)
- `LOG_FILE`: Log file name (default: "smma_slope_strategy_v5_log.txt")

### ALMA Strategy Parameters

- `ALMA_WINDOW`: Window size for ALMA calculation (default: 9)
- `ALMA_OFFSET`: Offset parameter for ALMA (default: 0.85)
- `ALMA_SIGMA`: Sigma parameter for ALMA (default: 6)
- `LOG_FILE`: Log file name (default: "alma_slope_strategy_v1_log.txt")