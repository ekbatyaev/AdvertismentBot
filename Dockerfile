FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/google-chrome

# -----------------------------
# System deps + Chrome (выполняется от root)
# -----------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libdrm2 \
    libglib2.0-0 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Установка Google Chrome
RUN wget -q -O /usr/share/keyrings/google-chrome.gpg \
        https://dl.google.com/linux/linux_signing_key.pub && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/* && \
    google-chrome --version

# -----------------------------
# Python deps
# -----------------------------
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------
# Настройка пользователя (после всех действий от root)
# -----------------------------
RUN useradd -m -u 1000 appuser && \
    mkdir -p /home/appuser/.cache/google-chrome /tmp/chrome-sessions && \
    chown -R appuser:appuser /home/appuser/.cache /tmp/chrome-sessions

USER appuser
ENV HOME=/home/appuser
ENV XDG_CACHE_HOME=/home/appuser/.cache

# -----------------------------
# Копирование приложения
# -----------------------------
COPY --chown=appuser:appuser . .

# -----------------------------
# Запуск (последняя команда!)
# -----------------------------
CMD ["python", "-u", "bot.py"]
