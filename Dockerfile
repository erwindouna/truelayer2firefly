FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=2.1.3
ENV PATH="/root/.local/bin:$PATH"

# Install system dependencies and Poetry
RUN apt-get update && apt-get install -y \
    curl build-essential git libssl-dev \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install only main dependencies and clean Poetry/pip cache
RUN poetry install --no-interaction --no-ansi --only main \
    && poetry cache clear pypi --all --no-interaction \
    && poetry cache clear packages --all --no-interaction \
    && rm -rf /root/.cache /root/.local/share/pypoetry

# Copy rest of the app
COPY . .

# Expose app port
EXPOSE 3000

# Run the app
CMD ["poetry", "run", "uvicorn", "truelayer2firefly:app", "--host", "0.0.0.0", "--port", "3000"]
