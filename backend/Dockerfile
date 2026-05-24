# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
RUN useradd -r -u 1001 -g root app
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=app:root app/ ./app/
USER 1001
EXPOSE 8000
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
