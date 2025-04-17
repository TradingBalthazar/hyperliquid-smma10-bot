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

# Create an entrypoint script that checks for RAILWAY_COMMAND
RUN echo '#!/bin/bash\n\
if [ -n "$RAILWAY_COMMAND" ]; then\n\
  echo "Running command: $RAILWAY_COMMAND"\n\
  exec $RAILWAY_COMMAND\n\
else\n\
  echo "Running default command: python smma_slope_strategy_v5.py"\n\
  exec python smma_slope_strategy_v5.py\n\
fi' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Use the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]