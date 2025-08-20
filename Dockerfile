# Use an official Python runtime as a parent image
FROM python:3.14.0rc2-trixie

# 1. Install system dependencies Playwright needs for Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /usr/src/app

# Copy requirements first (better for caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt || true

# Install Playwright browsers
# Store browsers outside /root to avoid being wiped
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/lib/playwright
RUN playwright install chromium

# Copy the rest of your project
COPY . .

# Run the script by default
CMD ["python", "orc_parallel.py"]