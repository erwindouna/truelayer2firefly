FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=1.8.2
ENV PATH="/root/.local/bin:$PATH"

# Install system dependencies and Poetry
RUN apt-get update && apt-get install -y curl build-essential git \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi --only main

# Copy the entire app (including static frontend files)
COPY . .

# Expose port
EXPOSE 8000

# Run the app
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
