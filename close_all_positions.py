#!/usr/bin/env python3

"""
Script to close all open positions on Hyperliquid
"""

from hyperliquid import HyperliquidSync
import json
import time
import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Authentication credentials
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "0x2ff3942d3b29dfd7e7226c6a46a42ff72d2e2f36f8bf617f9be1535751ed13fc")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0x42774353d90E9CbB1470f6A507161072fe873CCe")

# Trading parameters
SYMBOL = os.getenv("SYMBOL", "HYPE/USDC:USDC")
SLIPPAGE = 0.001  # 0.1% slippage tolerance for market orders

def log_message(message):
    """Log message to console"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)

def fetch_current_positions(api):
    """Fetch all current positions"""
    try:
        positions = api.fetch_positions([SYMBOL])
        
        if positions and len(positions) > 0:
            for position in positions:
                side = position.get('side', 'flat')
                size = float(position.get('contracts', 0))
                entry_price = float(position.get('entryPrice', 0))
                entry_value = size * entry_price
                
                log_message(f"Found position: {side.upper()} {size} {SYMBOL.split('/')[0]} @ {entry_price} (Value: ${entry_value:.2f})")
            
            return positions
        else:
            log_message("No current positions")
            return []
    
    except Exception as e:
        log_message(f"Error fetching positions: {e}")
        return []

def close_position(api, position):
    """Close a position"""
    try:
        side = position.get('side')
        size = position.get('contracts', 0)
        
        if not size or size == 0:
            log_message("No position to close")
            return None
        
        # Determine close side
        close_side = "sell" if side == "long" else "buy"
        
        # Get current price
        ticker = api.fetch_ticker(SYMBOL)
        current_price = ticker['last']
        
        # Calculate slippage price
        if close_side == "sell":
            slippage_price = current_price * (1 - SLIPPAGE)
        else:  # buy
            slippage_price = current_price * (1 + SLIPPAGE)
        
        # Place market order to close
        log_message(f"Closing {side} position of {size} {SYMBOL.split('/')[0]} with {close_side} order")
        
        params = {'reduceOnly': True}
        order = api.create_order(SYMBOL, 'market', close_side, size, slippage_price, params)
        
        log_message(f"Position closed: {json.dumps(order, indent=2)}")
        return order
    
    except Exception as e:
        log_message(f"Error closing position: {e}")
        return None

def close_all_positions():
    """Close all existing positions"""
    log_message("=== CLOSING ALL POSITIONS ===")
    
    # Initialize API client
    api = HyperliquidSync()
    api.privateKey = PRIVATE_KEY
    api.walletAddress = WALLET_ADDRESS
    
    log_message(f"Authenticated as: {WALLET_ADDRESS}")
    
    # Fetch current positions
    positions = fetch_current_positions(api)
    
    if not positions:
        log_message("No positions to close")
        return True
    
    # Close each position
    for position in positions:
        close_position(api, position)
    
    # Verify all positions are closed
    time.sleep(2)  # Wait for orders to process
    remaining_positions = fetch_current_positions(api)
    
    if not remaining_positions:
        log_message("All positions successfully closed")
        return True
    else:
        log_message(f"Warning: {len(remaining_positions)} positions still open")
        return False

if __name__ == "__main__":
    close_all_positions()