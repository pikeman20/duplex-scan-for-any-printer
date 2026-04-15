ARG BUILD_FROM
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /usr/src

ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install system dependencies
RUN \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-dev \
        cups \
        cups-client \
        cups-bsd \
        cups-ipp-utils \
        libcups2 \
        libcupsimage2 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Brother printer drivers
COPY drivers/*.deb /tmp/drivers/
RUN \
    dpkg -i /tmp/drivers/mfc7860dwlpr-2.1.0-1.i386.deb || true \
    && dpkg -i /tmp/drivers/cupswrapperMFC7860DW-2.0.4-2.i386.deb || true \
    && apt-get update && apt-get install -f -y \
    && rm -rf /tmp/drivers /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy application
WORKDIR /app
COPY src/ ./src/
COPY checkpoints/ ./checkpoints/

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /

COPY rootfs /

RUN chmod -R a+x /etc/s6-overlay/s6-rc.d
