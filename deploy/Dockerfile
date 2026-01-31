FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml ./
COPY app/ ./app/

# Install dependencies via uv
RUN uv pip install --system -e .

# Expose port
EXPOSE 8000

# Run
CMD ["python", "-m", "src.app.web"]
