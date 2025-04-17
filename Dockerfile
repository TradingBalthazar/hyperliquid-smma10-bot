FROM python:3.10-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the necessary files
COPY smma_slope_strategy_v5.py .
COPY close_all_positions.py .
COPY smma_calculation.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the strategy
CMD ["python", "smma_slope_strategy_v5.py"]