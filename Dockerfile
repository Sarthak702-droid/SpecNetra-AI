FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV OUTPUT_DIR=/app/output
ENV BROWSER_HEADLESS=true

# Install system dependencies needed for Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .
RUN python -m playwright install --with-deps chromium

COPY app/ ./app/
COPY inputs/ ./inputs/

CMD ["python", "-m", "app.main", "--requirements", "inputs/requirements.md", "--openapi", "inputs/openapi.json", "--scenarios", "inputs/scenarios.json"]
