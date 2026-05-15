ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12
FROM ${BUILD_FROM}

# base-python already includes Python 3.12.
# The environment is externally managed (PEP 668), so use a venv.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY app/ /app/
COPY rootfs/ /
COPY payloads/ /defaults/payloads/

EXPOSE 8765
