FROM python:3.11-slim

WORKDIR /app

# Avoid creating .pyc files and enforce stdout/stderr flush
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy code
COPY . /app

# Expose port from env
ENV PORT=8000
EXPOSE 8000

# Default command
CMD ["/bin/sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
