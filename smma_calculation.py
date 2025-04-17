def calculate_smma(df, period=10):
    """Calculate Smoothed Moving Average (SMMA)"""
    # First value is SMA
    smma = df['close'].rolling(window=period, min_periods=period).mean()
    
    # Calculate SMMA for the rest of the values
    for i in range(period, len(df)):
        smma.iloc[i] = (smma.iloc[i-1] * (period-1) + df['close'].iloc[i]) / period
    
    return smma
