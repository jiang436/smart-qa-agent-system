FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files (pyproject.toml + source)
COPY pyproject.toml ./
COPY src/ ./src/
COPY data/ ./data/

# Install dependencies via uv
RUN uv pip install --system -e .

# Expose port
EXPOSE 8000

# Run (uvicorn via CLI entry point)
CMD ["uv", "run", "smart-qa"]
