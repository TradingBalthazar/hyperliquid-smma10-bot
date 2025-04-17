FROM python:3.10-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all strategy files
COPY smma_slope_strategy_v5.py .
COPY close_all_positions.py .
COPY smma_calculation.py .
COPY alma_slope_strategy_v1.py .
COPY alma_calculation.py .
COPY run_alma_strategy.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default to running the SMMA strategy
# To run ALMA strategy, override CMD with: python run_alma_strategy.py
CMD ["python", "smma_slope_strategy_v5.py"]