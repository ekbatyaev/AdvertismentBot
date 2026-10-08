FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# -----------------------------
# System deps + Chromium (выполняется от root)
# Chromium из Debian собран и под amd64, и под arm64 — без эмуляции на Apple Silicon
# -----------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-liberation \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/* && \
    chromium --version && chromedriver --version

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
CMD ["python", "-u", "-m", "app.main"]
