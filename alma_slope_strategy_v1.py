#!/usr/bin/env python3

"""
Hyperliquid ALMA Slope Strategy (v1.0)

This strategy:
1. Uses a 9-period ALMA (Arnaud Legoux Moving Average)
2. Places aggressive buy orders when ALMA slope turns positive
3. Places aggressive sell orders when ALMA slope turns negative
4. Uses reduce-only orders to close 100% of existing positions when slope is opposite to position
5. Uses limit orders with pricing set for immediate execution
6. Ensures minimum order value is $10 to prevent order failures
7. Improved reduce-only logic to close positions when slope is opposite to position
8. Added position management for low margin situations (without closing positions)
"""

from hyperliquid import HyperliquidSync
import json
import time
import datetime
import pandas as pd
import numpy as np
import asyncio
import threading
import websockets
import os
from typing import Dict, List, Optional, Union, Any
from dotenv import load_dotenv
from alma_calculation import calculate_alma

# Load environment variables
load_dotenv()

# Authentication credentials
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "0x2ff3942d3b29dfd7e7226c6a46a42ff72d2e2f36f8bf617f9be1535751ed13fc")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0x42774353d90E9CbB1470f6A507161072fe873CCe")

# Trading parameters
SYMBOL = os.getenv("SYMBOL", "HYPE/USDC:USDC")
COIN = os.getenv("COIN", "HYPE")  # Used for websocket subscriptions
TIMEFRAME = os.getenv("TIMEFRAME", "1m")
LOOKBACK_PERIODS = int(os.getenv("LOOKBACK_PERIODS", "20"))  # Need at least a few periods for ALMA calculation
LEVERAGE = int(os.getenv("LEVERAGE", "3"))
# ALMA parameters
ALMA_WINDOW = int(os.getenv("ALMA_WINDOW", "9"))
ALMA_OFFSET = float(os.getenv("ALMA_OFFSET", "0.85"))
ALMA_SIGMA = float(os.getenv("ALMA_SIGMA", "6"))
SLOPE_LOOKBACK = int(os.getenv("SLOPE_LOOKBACK", "2"))  # Number of periods to calculate slope

# Order parameters
BASE_ORDER_SIZE = float(os.getenv("BASE_ORDER_SIZE", "0.65"))  # Base size in HYPE tokens
LEVEL_SPACING_PERCENT = float(os.getenv("LEVEL_SPACING_PERCENT", "0.0005"))  # 0.05% spacing between levels (tighter for aggressive orders)
NUM_LEVELS = int(os.getenv("NUM_LEVELS", "5"))  # More levels for aggressive orders
ORDER_REFRESH_SECONDS = int(os.getenv("ORDER_REFRESH_SECONDS", "10"))  # How often to refresh orders
MIN_ORDER_SIZE = float(os.getenv("MIN_ORDER_SIZE", "0.1"))  # Minimum order size to place
MIN_ORDER_VALUE = float(os.getenv("MIN_ORDER_VALUE", "10"))  # Minimum order value in USDC - MUST BE $10 to prevent order failures

# Position management parameters
MARGIN_SAFETY_FACTOR = float(os.getenv("MARGIN_SAFETY_FACTOR", "0.7"))  # Only use 70% of available margin
REDUCE_ONLY_THRESHOLD = float(os.getenv("REDUCE_ONLY_THRESHOLD", "15"))  # This threshold is no longer used (kept for backward compatibility)
POSITION_CHECK_INTERVAL = int(os.getenv("POSITION_CHECK_INTERVAL", "5"))  # Check positions every 5 seconds

# Log file
LOG_FILE = os.getenv("LOG_FILE", "alma_slope_strategy_v1_log.txt")

# Global variables
candle_data = None  # Will be initialized as DataFrame
current_price = 0
active_orders = []  # Track active orders
last_order_time = 0
alma_value = 0
alma_slope = 0  # Slope of the ALMA
previous_alma_slope = 0  # Previous slope direction for detecting changes
current_positions = []  # List to track multiple positions
initial_balance = 0
current_balance = 0
available_margin = 0
position_monitor_running = False
slope_direction_changed = False  # Flag to indicate if slope direction has changed
last_position_check_time = 0  # Track when we last checked positions

def log_message(message):
    """Log message to console and file"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    
    with open(LOG_FILE, "a") as f:
        f.write(log_entry + "\n")

def fetch_balance(api):
    """Fetch current account balance"""
    try:
        balance = api.fetch_balance()
        if balance and 'total' in balance and 'USDC' in balance['total']:
            usdc_balance = balance['total']['USDC']
            log_message(f"Current USDC balance: {usdc_balance}")
            return usdc_balance
        return 0
    except Exception as e:
        log_message(f"Error fetching balance: {e}")
        return 0

def fetch_available_margin(api):
    """Fetch available margin for trading"""
    global available_margin
    
    try:
        balance = api.fetch_balance()
        if balance and 'free' in balance and 'USDC' in balance['free']:
            free_usdc = balance['free']['USDC']
            # Apply safety factor to avoid using all available margin
            available_margin = free_usdc * MARGIN_SAFETY_FACTOR
            log_message(f"Available margin: ${available_margin}")
            return available_margin
        return 0
    except Exception as e:
        log_message(f"Error fetching available margin: {e}")
        return 0

def fetch_current_positions(api):
    """Fetch all current positions"""
    global current_positions
    
    try:
        positions = api.fetch_positions([SYMBOL])
        
        if positions and len(positions) > 0:
            current_positions = []
            
            for position in positions:
                position_id = position.get('id', str(time.time()))
                side = position.get('side', 'flat')
                size = float(position.get('contracts', 0))
                entry_price = float(position.get('entryPrice', 0))
                entry_value = size * entry_price
                
                # Skip flat positions
                if side == 'flat' or size == 0:
                    continue
                
                # Create position object
                position_obj = {
                    "id": position_id,
                    "side": side,
                    "size": size,
                    "entry_price": entry_price,
                    "entry_value": entry_value,
                    "entry_time": time.time()
                }
                
                current_positions.append(position_obj)
                
                log_message(f"Position: {side.upper()} {size} {COIN} @ {entry_price} (Value: ${entry_value:.2f})")
            
            return current_positions
        else:
            current_positions = []
            log_message("No current positions")
            return []
    
    except Exception as e:
        log_message(f"Error fetching positions: {e}")
        return []

def close_all_positions(api):
    """Close all existing positions"""
    try:
        log_message("Closing all existing positions...")
        
        # Fetch current positions
        positions = fetch_current_positions(api)
        
        if not positions:
            log_message("No positions to close")
            return True
        
        for position in positions:
            if position["side"] == "flat" or position["size"] == 0:
                continue
                
            # Determine close side
            close_side = "sell" if position["side"] == "long" else "buy"
            size = position["size"]
            
            # Place limit order to close at current price
            log_message(f"Closing {position['side']} position of {size} {COIN} with {close_side} limit order")
            
            params = {'reduceOnly': True}
            
            # For long positions, sell at slightly below current price
            # For short positions, buy at slightly above current price
            # This ensures the orders get filled quickly
            if close_side == "sell":
                price = current_price * 0.999  # 0.1% below current price
            else:
                price = current_price * 1.001  # 0.1% above current price
                
            order = api.create_order(SYMBOL, 'limit', close_side, size, price, params)
            
            log_message(f"Position close order placed: {json.dumps(order, indent=2)}")
        
        return True
    
    except Exception as e:
        log_message(f"Error closing positions: {e}")
        return False

def calculate_alma_slope():
    """Calculate ALMA and its slope"""
    global candle_data, alma_value, alma_slope, previous_alma_slope, slope_direction_changed
    
    if candle_data is None or len(candle_data) < ALMA_WINDOW + SLOPE_LOOKBACK:
        log_message(f"Not enough data to calculate ALMA. Need at least {ALMA_WINDOW + SLOPE_LOOKBACK} periods.")
        return
    
    try:
        # Calculate ALMA
        df = candle_data.copy()
        alma = calculate_alma(df, window=ALMA_WINDOW, offset=ALMA_OFFSET, sigma=ALMA_SIGMA)
        df['alma'] = alma
        
        # Get the current ALMA value
        alma_value = df['alma'].iloc[-1]
        
        # Store previous slope direction
        previous_slope_direction = 1 if previous_alma_slope > 0 else -1 if previous_alma_slope < 0 else 0
        
        # Calculate slope (current ALMA - ALMA from SLOPE_LOOKBACK periods ago)
        current_alma = df['alma'].iloc[-1]
        previous_alma = df['alma'].iloc[-1-SLOPE_LOOKBACK]
        alma_slope = (current_alma - previous_alma) / previous_alma  # Percentage change
        
        # Get current slope direction
        current_slope_direction = 1 if alma_slope > 0 else -1 if alma_slope < 0 else 0
        
        # Check if slope direction has changed
        if previous_slope_direction != 0 and current_slope_direction != 0:
            if previous_slope_direction != current_slope_direction:
                slope_direction_changed = True
                log_message(f"ALMA SLOPE DIRECTION CHANGED: {previous_slope_direction} -> {current_slope_direction}")
            else:
                slope_direction_changed = False
        
        # Update previous slope for next calculation
        previous_alma_slope = alma_slope
        
        if alma_slope > 0:
            log_message(f"ALMA: {alma_value:.4f}, Slope: POSITIVE ({alma_slope*100:.4f}%)")
        else:
            log_message(f"ALMA: {alma_value:.4f}, Slope: NEGATIVE ({alma_slope*100:.4f}%)")
        
        return alma_value, alma_slope
    
    except Exception as e:
        log_message(f"Error calculating ALMA: {e}")
        return None, None

def fetch_initial_data(api):
    """Fetch initial data to bootstrap the strategy"""
    global candle_data, current_price, initial_balance, current_balance, available_margin
    
    log_message("Fetching initial market data...")
    
    try:
        # Fetch OHLCV data
        ohlcv = api.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=LOOKBACK_PERIODS)
        
        # Convert to pandas DataFrame
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        candle_data = df
        current_price = df['close'].iloc[-1]
        
        log_message(f"Fetched {len(df)} candles for {SYMBOL}")
        log_message(f"Current price: {current_price}")
        
        # Calculate initial ALMA
        calculate_alma_slope()
        
        # Set leverage
        leverage_result = api.set_leverage(LEVERAGE, SYMBOL)
        log_message(f"Leverage set to {LEVERAGE}x: {leverage_result}")
        
        # Fetch initial balance
        initial_balance = fetch_balance(api)
        current_balance = initial_balance
        log_message(f"Initial balance: ${initial_balance}")
        
        # Fetch available margin
        available_margin = fetch_available_margin(api)
        
        # Fetch current positions
        fetch_current_positions(api)
        
        # Cancel any existing orders
        cancel_all_orders(api)
        
        return True
    
    except Exception as e:
        log_message(f"Error fetching initial data: {e}")
        return False

def update_candle_data(trade_data):
    """Update candle data with new trade information"""
    global candle_data, current_price
    
    if not trade_data or candle_data is None or candle_data.empty:
        return
    
    try:
        # Extract trade information
        price = trade_data.get('price', 0)
        amount = trade_data.get('amount', 0)
        timestamp = trade_data.get('timestamp', 0)
        
        if price > 0:
            current_price = price
        
        # Get the latest candle
        latest_candle = candle_data.iloc[-1]
        latest_timestamp = latest_candle['timestamp']
        
        # Check if this trade belongs to the current candle or a new one
        trade_dt = pd.to_datetime(timestamp, unit='ms')
        
        # If this is a new minute, create a new candle
        if trade_dt.minute != latest_timestamp.minute or trade_dt.hour != latest_timestamp.hour:
            # Create a new candle
            new_candle = {
                'timestamp': trade_dt,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': amount
            }
            
            # Append to candle data
            candle_data = pd.concat([candle_data, pd.DataFrame([new_candle])], ignore_index=True)
            
            # Remove oldest candle if we exceed lookback periods
            if len(candle_data) > LOOKBACK_PERIODS:
                candle_data = candle_data.iloc[1:].reset_index(drop=True)
                
            # Recalculate ALMA when a new candle is created
            calculate_alma_slope()
        else:
            # Update the current candle
            idx = len(candle_data) - 1
            candle_data.at[idx, 'high'] = max(candle_data.at[idx, 'high'], price)
            candle_data.at[idx, 'low'] = min(candle_data.at[idx, 'low'], price)
            candle_data.at[idx, 'close'] = price
            candle_data.at[idx, 'volume'] += amount
    
    except Exception as e:
        log_message(f"Error updating candle data: {e}")

def cancel_all_orders(api):
    """Cancel all open orders"""
    global active_orders
    
    try:
        log_message("Cancelling all open orders...")
        
        # Fetch open orders
        open_orders = api.fetch_open_orders(SYMBOL)
        
        if open_orders:
            for order in open_orders:
                order_id = order.get('id')
                if order_id:
                    api.cancel_order(order_id, SYMBOL)
                    log_message(f"Cancelled order {order_id}")
        
        active_orders = []
        log_message(f"Cancelled {len(open_orders)} open orders")
        
        return True
    
    except Exception as e:
        log_message(f"Error cancelling orders: {e}")
        return False

def calculate_position_size(api):
    """Calculate position size based on available margin and minimum order value"""
    global available_margin
    
    try:
        # Get available margin
        available_margin = fetch_available_margin(api)
        
        # If available margin is below minimum order value, return 0
        if available_margin < MIN_ORDER_VALUE:
            log_message(f"Available margin (${available_margin:.2f}) is below minimum order value (${MIN_ORDER_VALUE})")
            return 0
        
        # Calculate position size based on available margin
        margin_based_position_value = available_margin * LEVERAGE
        
        # Convert to position size
        position_size = margin_based_position_value / current_price
        
        # Note: No need to adjust for leverage again as we've already accounted for it
        
        # Calculate the minimum size needed to meet MIN_ORDER_VALUE
        min_size_for_value = MIN_ORDER_VALUE / current_price
        
        # Use the larger of calculated size and minimum size
        position_size = max(position_size, min_size_for_value)
        
        # Ensure minimum order size
        if position_size < MIN_ORDER_SIZE:
            log_message(f"Calculated position size {position_size} is below minimum {MIN_ORDER_SIZE}, using minimum")
            position_size = MIN_ORDER_SIZE
        
        # Double-check if order value meets minimum
        order_value = position_size * current_price
        if order_value < MIN_ORDER_VALUE:
            log_message(f"Order value ${order_value:.2f} is below minimum ${MIN_ORDER_VALUE}, adjusting size")
            position_size = MIN_ORDER_VALUE / current_price
        
        log_message(f"Calculated position size: {position_size} {COIN} (Value: ${position_size * current_price:.2f})")
        
        return position_size
    
    except Exception as e:
        log_message(f"Error calculating position size: {e}")
        return 0

def has_position():
    """Check if we have any position"""
    return len(current_positions) > 0

def get_position_side():
    """Get the side of the current position (long or short)"""
    if not current_positions:
        return None
    
    # Return the side of the first position
    return current_positions[0]["side"]

def should_use_reduce_only(side):
    """
    Determine if we should use reduce-only orders based on:
    1. If there's an opposite position
    2. If the current slope direction is opposite to our position
    """
    if not current_positions:
        return False
    
    # Check for opposite position
    for position in current_positions:
        # Case 1: Opposite position exists
        if (position["side"] == "long" and side == "sell") or \
           (position["side"] == "short" and side == "buy"):
            log_message(f"Using reduce-only because opposite position exists")
            return True
    
    # Case 2: Current slope direction is opposite to our position
    # If slope is positive, we should be in long positions
    # If slope is negative, we should be in short positions
    for position in current_positions:
        if (alma_slope > 0 and position["side"] == "short") or \
           (alma_slope < 0 and position["side"] == "long"):
            log_message(f"Using reduce-only because current slope direction ({alma_slope > 0 and 'positive' or 'negative'}) is opposite to position ({position['side']})")
            return True
    
    # Case 3: Slope direction changed and we have a position (keeping this for backward compatibility)
    if slope_direction_changed and current_positions:
        log_message(f"Using reduce-only because slope direction changed with existing position")
        return True
    
    return False

def get_reduce_only_side():
    """Determine which side to use for reduce-only orders based on current positions"""
    if not current_positions:
        return None
    
    # If we have a long position, use sell to reduce
    # If we have a short position, use buy to reduce
    for position in current_positions:
        if position["side"] == "long":
            return "sell"
        elif position["side"] == "short":
            return "buy"
    
    return None

def place_reduce_only_orders(api, side=None):
    """Place reduce-only orders to manage existing positions"""
    global active_orders, last_order_time
    
    try:
        # If side is not specified, determine it based on current positions
        if side is None:
            side = get_reduce_only_side()
            if side is None:
                log_message("No positions to reduce")
                return False
        
        # Find positions that can be reduced with the given side
        reducible_positions = []
        for position in current_positions:
            if (position["side"] == "long" and side == "sell") or \
               (position["side"] == "short" and side == "buy"):
                reducible_positions.append(position)
        
        if not reducible_positions:
            log_message(f"No positions to reduce with {side} orders")
            return False
        
        # Place reduce-only orders for each position
        orders_placed = 0
        for position in reducible_positions:
            # Calculate size to reduce (use 100% of position size)
            reduce_size = position["size"]
            
            # Ensure minimum order value
            order_value = reduce_size * current_price
            if order_value < MIN_ORDER_VALUE:
                # If position is too small to split, use full size
                if position["size"] * current_price < MIN_ORDER_VALUE * 2:
                    reduce_size = position["size"]
                else:
                    # Otherwise adjust to meet minimum
                    reduce_size = MIN_ORDER_VALUE / current_price
            
            # Set price slightly better than market for quick execution
            if side == "sell":
                price = current_price * 0.999  # 0.1% below current price
            else:
                price = current_price * 1.001  # 0.1% above current price
            
            # Place reduce-only order
            params = {'reduceOnly': True}
            log_message(f"Placing REDUCE-ONLY {side.upper()} order: {reduce_size} {COIN} @ {price} (Value: ${reduce_size * price:.2f})")
            
            try:
                order = api.create_order(SYMBOL, 'limit', side, reduce_size, price, params)
                active_orders.append(order)
                orders_placed += 1
            except Exception as e:
                log_message(f"Error placing reduce-only order: {e}")
        
        last_order_time = time.time()
        log_message(f"Placed {orders_placed} reduce-only orders")
        
        return orders_placed > 0
    
    except Exception as e:
        log_message(f"Error placing reduce-only orders: {e}")
        return False

def manage_positions_for_low_margin(api):
    """Manage positions when margin is low"""
    global available_margin, last_position_check_time, alma_slope
    
    # Only check periodically to avoid too many API calls
    current_time = time.time()
    if current_time - last_position_check_time < POSITION_CHECK_INTERVAL:
        return
    
    last_position_check_time = current_time
    
    try:
        # Update available margin
        available_margin = fetch_available_margin(api)
        
        # Update current positions
        fetch_current_positions(api)
        
        # Always check if we have positions in the opposite direction of the slope
        # This is now a separate check from the low margin condition
        for position in current_positions:
            if (alma_slope > 0 and position["side"] == "short") or \
               (alma_slope < 0 and position["side"] == "long"):
                log_message(f"CRITICAL: Detected position ({position['side']}) opposite to slope direction ({alma_slope > 0 and 'positive' or 'negative'})")
                log_message(f"Closing positions with reduce-only orders (doesn't require margin)")
                # Close positions with reduce-only orders - this doesn't require margin
                close_all_positions(api)
                return True
        
        # If margin is low, just log it
        if available_margin < MIN_ORDER_VALUE and has_position():
            log_message(f"Low margin detected (${available_margin:.2f}), but not closing positions as they align with slope direction")
            # Per user request: if there's not enough margin to open a trade, do nothing
            return
            
    except Exception as e:
        log_message(f"Error managing positions for low margin: {e}")
        return False

def place_aggressive_orders(api):
    """Place aggressive orders based on ALMA slope"""
    global available_margin, slope_direction_changed
    
    try:
        # Get current time
        current_time = time.time()
        # Cancel existing orders before placing new ones
        cancel_all_orders(api)
        
        # Update available margin and positions
        available_margin = fetch_available_margin(api)
        fetch_current_positions(api)
        
        # Determine order side based on ALMA slope
        if alma_slope > 0:
            # Positive slope - place buy orders
            order_side = "buy"
            log_message("Placing aggressive BUY orders due to positive ALMA slope")
        else:
            # Negative slope - place sell orders
            order_side = "sell"
            log_message("Placing aggressive SELL orders due to negative ALMA slope")
        
        # CRITICAL: Always check for positions in the opposite direction of the slope
        # This check happens regardless of margin
        for position in current_positions:
            if (alma_slope > 0 and position["side"] == "short") or \
               (alma_slope < 0 and position["side"] == "long"):
                log_message(f"CRITICAL: Detected position ({position['side']}) opposite to slope direction ({alma_slope > 0 and 'positive' or 'negative'})")
                log_message(f"Closing positions with reduce-only orders (doesn't require margin)")
                # Close positions with reduce-only orders - this doesn't require margin
                close_all_positions(api)
                return True
        
        # If margin is low, just log it and return
        if available_margin < MIN_ORDER_VALUE:
            log_message(f"Available margin (${available_margin:.2f}) is too low to place orders. Minimum: ${MIN_ORDER_VALUE}")
            return False
        
        # Check if we should use reduce-only orders
        reduce_only = should_use_reduce_only(order_side)
        
        # If we should use reduce-only orders, place them and exit
        if reduce_only:
            return place_reduce_only_orders(api, order_side)
        
        # If available margin is too low, don't place new orders and don't try to reduce positions
        if available_margin < MIN_ORDER_VALUE:
            log_message(f"Available margin (${available_margin:.2f}) is too low to place orders. Minimum: ${MIN_ORDER_VALUE}")
            return False
        
        # Calculate base price
        base_price = current_price
        
        # Calculate order levels
        order_levels = []
        
        # For buy orders, place below current price
        # For sell orders, place above current price
        for i in range(NUM_LEVELS):
            level_multiplier = (i + 1) * LEVEL_SPACING_PERCENT
            
            if order_side == "buy":
                # Place buy orders slightly above current price for immediate execution
                price = base_price * (1 + level_multiplier)
            else:
                # Place sell orders slightly below current price for immediate execution
                price = base_price * (1 - level_multiplier)
            
            order_levels.append(price)
        
        # Calculate position size
        base_order_size = calculate_position_size(api)
        
        # If we can't calculate a valid position size, exit
        if base_order_size <= 0:
            log_message("Cannot calculate a valid position size, skipping order placement")
            return False
        
        # Calculate how many levels we can afford
        max_order_value = available_margin * LEVERAGE
        level_order_value = base_order_size * current_price
        
        # Calculate affordable levels - base_order_size already includes leverage
        affordable_levels = int(max_order_value / level_order_value)
        
        # Limit to a reasonable number to avoid over-leveraging
        affordable_levels = min(affordable_levels, 3)
        
        log_message(f"Can afford {affordable_levels} order levels with available margin ${available_margin:.2f}")
        
        # Limit number of levels based on what we can afford
        num_levels = min(NUM_LEVELS, affordable_levels)
        
        if num_levels == 0:
            log_message("Not enough margin to place any orders")
            return False
        
        # Place orders
        orders_placed = 0
        
        for i in range(num_levels):
            # Size increases for levels further from base price
            size_multiplier = 1 + (i * 0.5)  # 50% increase per level for more aggressive sizing
            level_order_size = base_order_size * size_multiplier
            
            # Calculate order value
            order_value = level_order_size * order_levels[i]
            
            # Skip if order value is too small
            if order_value < MIN_ORDER_VALUE:
                log_message(f"Skipping {order_side.upper()} #{i+1}: Order value ${order_value:.2f} below minimum ${MIN_ORDER_VALUE}")
                continue
            
            log_message(f"Placing {order_side.upper()} #{i+1}: {level_order_size} {COIN} @ {order_levels[i]} (Value: ${order_value:.2f})")
            
            # Set reduce-only parameter if needed
            params = {}
            
            try:
                order = api.create_order(SYMBOL, 'limit', order_side, level_order_size, order_levels[i], params)
                active_orders.append(order)
                orders_placed += 1
            except Exception as e:
                log_message(f"Error placing {order_side} order: {e}")
        
        last_order_time = current_time
        slope_direction_changed = False  # Reset the flag
        log_message(f"Placed {orders_placed} {order_side.upper()} orders")
        
        return True
    
    except Exception as e:
        log_message(f"Error placing aggressive orders: {e}")
        return False

def order_management_thread(api):
    """Thread to manage orders"""
    log_message("Starting order management thread")
    
    last_slope_log_time = 0
    
    try:
        while True:
            current_time = time.time()
            
            # Update positions and margin periodically
            if int(current_time) % 60 == 0:  # Every minute
                fetch_available_margin(api)
                fetch_current_positions(api)
            
            # Log ALMA slope every 10 seconds
            if current_time - last_slope_log_time >= 10:
                calculate_alma_slope()
                last_slope_log_time = current_time
            
            # Check if we need to manage positions for low margin
            manage_positions_for_low_margin(api)
            
            # Place/refresh orders based on ALMA slope
            place_aggressive_orders(api)
            
            # Sleep to avoid high CPU usage
            time.sleep(1)
    
    except KeyboardInterrupt:
        log_message("Order management thread stopped by user")
    except Exception as e:
        log_message(f"Error in order management thread: {e}")
    
    finally:
        log_message("Order management thread stopped")

async def process_trade_message(message):
    """Process trade message"""
    global current_price
    
    try:
        if isinstance(message, dict) and 'data' in message:
            data = message.get('data', [])
            
            # Check if this is a trades update
            if isinstance(data, list) and len(data) > 0:
                # Update current price from the most recent trade
                for trade in data:
                    if isinstance(trade, dict) and 'px' in trade:
                        current_price = float(trade['px'])
                        
                        # Update candle data
                        trade_data = {
                            'price': float(trade.get('px', 0)),
                            'amount': float(trade.get('sz', 0)),
                            'timestamp': int(trade.get('time', 0))
                        }
                        update_candle_data(trade_data)
    
    except Exception as e:
        log_message(f"Error processing trade message: {e}")

async def websocket_handler(api):
    """Handle websocket connections and messages"""
    ws_base_url = "wss://api.hyperliquid.xyz/ws"
    
    log_message("Starting websocket connections...")
    
    while True:
        try:
            # Connect to websocket
            async with websockets.connect(ws_base_url) as ws:
                # Subscribe to trade updates
                trades_sub = {
                    "method": "subscribe",
                    "subscription": {
                        "type": "trades",
                        "coin": COIN
                    }
                }
                await ws.send(json.dumps(trades_sub))
                log_message(f"Subscribed to {COIN} trade updates")
                
                # Process incoming messages
                while True:
                    try:
                        message = await ws.recv()
                        message_data = json.loads(message)
                        
                        # Determine message type and process accordingly
                        if 'channel' in message_data:
                            channel = message_data.get('channel', '')
                            
                            if channel == 'trades':
                                await process_trade_message(message_data)
                    
                    except websockets.exceptions.ConnectionClosed:
                        log_message("Websocket connection closed")
                        break
        
        except Exception as e:
            log_message(f"Websocket error: {e}")
        
        log_message("Reconnecting websocket in 5 seconds...")
        await asyncio.sleep(5)

def run_strategy():
    """Run the ALMA Slope Strategy"""
    log_message("=== STARTING ALMA SLOPE STRATEGY (V1.0) ===")
    log_message(f"Symbol: {SYMBOL}")
    log_message(f"ALMA Parameters: Window={ALMA_WINDOW}, Offset={ALMA_OFFSET}, Sigma={ALMA_SIGMA}")
    log_message(f"Order Levels: {NUM_LEVELS}")
    log_message(f"Level Spacing: {LEVEL_SPACING_PERCENT*100}% (aggressive)")
    log_message(f"Strategy Logic: Buy aggressively when ALMA slope is positive, sell aggressively when negative")
    log_message(f"Using reduce-only orders for opposite positions and when slope is opposite to position")
    log_message(f"Using limit orders only")
    log_message(f"Minimum Order Value: ${MIN_ORDER_VALUE} (required to prevent order failures)")
    log_message(f"Reduce-Only Threshold: ${REDUCE_ONLY_THRESHOLD}")
    log_message(f"Leverage: {LEVERAGE}x")
    
    # Initialize API client
    api = HyperliquidSync()
    api.privateKey = PRIVATE_KEY
    api.walletAddress = WALLET_ADDRESS
    
    log_message(f"Authenticated as: {WALLET_ADDRESS}")
    
    # Fetch initial data
    if not fetch_initial_data(api):
        log_message("Failed to fetch initial data, exiting")
        return
    
    # Start order management thread
    order_thread = threading.Thread(target=order_management_thread, args=(api,))
    order_thread.daemon = True
    order_thread.start()
    
    try:
        # Run the websocket handler
        asyncio.run(websocket_handler(api))
    
    except KeyboardInterrupt:
        log_message("\nStrategy stopped by user")
    except Exception as e:
        log_message(f"Strategy error: {e}")
    
    # Clean up
    cancel_all_orders(api)
    
    log_message("=== STRATEGY EXECUTION COMPLETED ===")

if __name__ == "__main__":
    # Create or clear log file
    with open(LOG_FILE, "w") as f:
        f.write(f"=== ALMA SLOPE STRATEGY V1 LOG - {datetime.datetime.now()} ===\n\n")
    
    # Run strategy
    run_strategy()