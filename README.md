# 🤖 Legal Bot — Telegram-бот для проверки рекламы

Telegram-бот для анализа сообщений и постов Telegram-каналов на предмет **нарушений рекламного законодательства РФ**.  
Использует LLM (YandexGPT) + базу знаний и формирует понятные рекомендации и отчёты.

---

## 🚀 Возможности

- ✅ Проверка **одного сообщения**
- 🗂 Анализ **Telegram-каналов**:
  - все посты
  - за период
  - за неделю / месяц / год
- 📊 Формирование **Excel-отчёта** по каналу
- ⚖️ Определение:
  - наличия нарушений
  - статьи закона
  - максимального штрафа
  - рекомендаций по исправлению
- 🧠 Интеграция с **Yandex Cloud (YandexGPT + Vector Store)**

---

## 🏗 Архитектура проекта

```

.
├── bot.py                 # Telegram-бот (aiogram)
├── model_ask.py           # Запросы к LLM + логирование ответов
├── channel_parse.py       # Парсинг Telegram-каналов через Selenium
├── logging_config.py      # Конфигурация логирования
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── logs/                  # Логи и статистика

````

---

## 🔧 Требования

- Docker + docker-compose
- Telegram Bot Token
- Доступ к Yandex Cloud:
  - API Key
  - Folder ID
  - Vector Store ID

---

## ⚙️ Переменные окружения

Создай файл `.env` на основе `.env.example`:

```env
TELEGRAM_BOT_API_TOKEN=your_telegram_token

YANDEX_CLOUD_MODEL=yandexgpt
YANDEX_CLOUD_FOLDER=your_folder_id
YANDEX_CLOUD_API_KEY=your_api_key

VECTOR_STORE_ID=your_vector_store_id
````

---

## 🐳 Запуск через Docker

```bash
docker compose build
docker compose up -d
```

Бот начнёт polling Telegram API автоматически.

---

## 🧪 Локальный запуск (без Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
```

⚠️ Для парсинга каналов требуется Google Chrome.

---

## 📊 Логи и статистика

* Все ответы модели логируются в `logs/*.json`
* Доступна скрытая команда администратора:

```
/secret_admin_statistics_request
```

Она возвращает:

* количество запросов
* средние токены
* среднее время ответа
* файл со статистикой

---

## ⚠️ Важно

* Парсинг Telegram-каналов выполняется через **Selenium**
* Частые запросы могут приводить к блокировкам со стороны Telegram
* Используй прокси / лимиты при масштабировании
