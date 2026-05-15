# Multi-arch base image (amd64 + aarch64) with Python 3.12 pre-installed.
ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.12-alpine3.23
FROM ${BUILD_FROM}

# Python is externally managed (PEP 668), so use a venv.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY app/ /app/
COPY rootfs/ /
COPY payloads/ /defaults/payloads/

EXPOSE 8765
