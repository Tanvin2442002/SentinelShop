# syntax=docker/dockerfile:1

FROM python:3.12-alpine AS builder
WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


FROM python:3.12-alpine AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1


RUN addgroup -S -g 10001 app \
 && adduser -S -u 10001 -G app -H -s /sbin/nologin app

WORKDIR /srv
COPY --from=builder /opt/venv /opt/venv
COPY worker ./worker

RUN apk upgrade --no-cache

USER 10001:10001
EXPOSE 9100


HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9100/metrics', timeout=2)"]

CMD ["python", "-m", "worker"]
