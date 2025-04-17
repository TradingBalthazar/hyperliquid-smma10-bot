import numpy as np

def calculate_alma(df, window=9, offset=0.85, sigma=6):
    """Calculate Arnaud Legoux Moving Average (ALMA)
    
    Parameters:
        df: DataFrame with 'close' column
        window: Window size (default: 9)
        offset: Gaussian offset (default: 0.85)
        sigma: Gaussian sigma (default: 6)
    
    Returns:
        numpy array of ALMA values
    """
    series = df['close'].values
    alma_values = np.full_like(series, np.nan, dtype=float)
    
    # Calculate Gaussian weights
    m = offset * (window - 1)
    s = window / sigma
    weights = np.exp(-((np.arange(window) - m) ** 2) / (2 * s ** 2))
    weights /= weights.sum()  # Normalize weights
    
    # Calculate ALMA
    for i in range(window - 1, len(series)):
        window_data = series[i - window + 1:i + 1]
        alma_values[i] = np.dot(window_data, weights)
    
    return alma_values