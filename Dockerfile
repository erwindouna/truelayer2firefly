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


#RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
#    && apt-get install -y nodejs

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi --only main \
    && poetry cache clear . --all \
    && rm -rf /root/.cache /root/.local/share/pypoetry

COPY . .

# TODO: check this later, since it will change
EXPOSE 3000

# Run the app
# TODO: work on this later, to make it more flexible
CMD ["poetry", "run", "uvicorn", "truelayer2firefly:app", "--host", "0.0.0.0", "--port", "3000"]
