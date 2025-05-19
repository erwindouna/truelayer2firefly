# Stage 1: Builder
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.2
ENV PATH="/root/.local/bin:$PATH"
RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.in-project true \
    && poetry install --no-dev --no-interaction --no-ansi \
    && rm -rf /root/.cache

COPY . .

# Stage 2: Final Image
FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

# Expose port (update if needed)
EXPOSE 3000

CMD ["uvicorn", "truelayer2firefly:app", "--host", "0.0.0.0", "--port", "3000"]
