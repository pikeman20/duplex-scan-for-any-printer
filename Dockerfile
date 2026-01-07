ARG BUILD_FROM
FROM $BUILD_FROM

# Set S6 wait time
ENV S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
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
RUN dpkg -i /tmp/drivers/mfc7860dwlpr-2.1.0-1.i386.deb || true && \
    dpkg -i /tmp/drivers/cupswrapperMFC7860DW-2.0.4-2.i386.deb || true && \
    apt-get update && apt-get install -f -y && \
    rm -rf /tmp/drivers /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt /tmp/
RUN pip3 install --break-system-packages -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Copy application
WORKDIR /app
COPY src/ ./src/
COPY checkpoints/ ./checkpoints/

# Copy rootfs (S6 services)
COPY rootfs/ /

# Make scripts executable
RUN chmod +x /etc/cont-init.d/*.sh && \
    chmod +x /etc/services.d/*/run && \
    chmod +x /etc/services.d/*/finish

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Labels
LABEL \
    io.hass.name="Scan Agent" \
    io.hass.description="Brother Scanner FTP receiver with PDF generation and printing" \
    io.hass.arch="armhf|armv7|aarch64|amd64|i386" \
    io.hass.type="addon" \
    io.hass.version="1.0.0"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD test -d /share/scan_inbox || exit 1

# S6 will handle starting services
CMD []
