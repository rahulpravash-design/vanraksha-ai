FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Install the engine first (rarely changes) so this layer caches well.
COPY services/ai-engine /engine
RUN pip install --no-cache-dir -e /engine

COPY services/api/pyproject.toml /app/pyproject.toml
COPY services/api/app /app/app
RUN pip install --no-cache-dir -e /app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
