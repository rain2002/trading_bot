# Multi-stage production Dockerfile for Institutional Quant Hedge Fund Bot
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runner

WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 quantuser

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN chown -R quantuser:quantuser /app
USER quantuser

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Container healthcheck verifying core modules load
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "from trading_system.app.features.regime import UniversalLocalIndexRegimeEngine; print('OK')" || exit 1

CMD ["python", "trading_system/scripts/run_manager.py", "--mode", "PAPER"]
