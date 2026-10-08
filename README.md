# 🤖 Advertisment Bot: Telegram-бот для проверки рекламы

Telegram-бот анализирует сообщения и посты Telegram-каналов на **нарушения рекламного законодательства РФ**.
Использует YandexGPT и собственную базу знаний (законы, разъяснения ФАС и ЦБ), выдаёт описание нарушений, размер штрафа и рекомендации, формирует Excel-отчёты.

---

## 🚀 Возможности

- ✅ Проверка **одного сообщения** (текст или подпись к медиа)
- 🗂 Анализ **Telegram-канала**:
  - все посты
  - за неделю / месяц / год
  - за произвольный период
- 📊 **Excel-отчёт** по каналу
- ⚖️ По каждому нарушению:
  - есть ли нарушение
  - объяснение со ссылками на статьи
  - максимальный штраф
  - рекомендация по исправлению
- 📚 Ответы строятся на **выдержках из базы знаний** (Yandex AI Studio Vector Store)

---

## 🧠 Как работает анализ

```
текст рекламы
   │
   ├─▶ 1. Поиск по базе знаний (Vector Store API) → релевантные выдержки
   │
   └─▶ 2. Запрос к YandexGPT (Responses API) с выдержками в промпте
          и строгой JSON-схемой ответа (text.format = json_schema)
                │
                └─▶ {"analysis": [{violations, description, fine, recommendation}, ...]}
```

Почему поиск отделён от генерации: Yandex AI Studio **не позволяет** использовать в одном запросе инструменты (`tools`, в том числе `file_search`) и структурированный вывод ([документация](https://aistudio.yandex.ru/docs/ru/ai-studio/concepts/generation/structured-output.html)). Поэтому поиск выполняется отдельным запросом, а найденные выдержки передаются модели в тексте.

---

## 🏗 Структура проекта

```
.
├── app/
│   ├── main.py                    # Точка входа: запуск polling
│   ├── settings.py                # Настройки из .env, логирование (loguru)
│   ├── functions.py               # Чтение/атомарная запись JSON-логов
│   ├── ai/
│   │   ├── client.py              # Клиент Yandex AI Studio: генерация + поиск по Vector Store
│   │   ├── models.py              # Модели ответов клиента
│   │   └── functions/
│   │       └── ad_analysis.py     # Промпт, JSON-схема, анализ текста, логирование результата
│   ├── bot/
│   │   ├── config.py              # Bot и Dispatcher (aiogram)
│   │   ├── routers.py             # Обработчики команд и кнопок
│   │   ├── functions.py           # Анализ канала, Excel-отчёт, валидация дат
│   │   ├── keyboards.py           # Клавиатуры
│   │   └── states.py              # FSM-состояния
│   └── parser/
│       ├── driver.py              # Настройка Selenium / Chromium
│       └── telegram_web_parser.py # Парсинг t.me/s/<канал>
├── docs/
│   └── all_law_ad_text.txt        # Исходные тексты базы знаний
├── scripts/
│   ├── create_vector_store.py     # Создание векторного хранилища из docs/
│   └── ...                        # Прочие старые скрипты
├── logs/                          # app.log и ai_logs/*.json (монтируется в Docker)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 🔧 Требования

- Docker и Docker Compose (или Python 3.12 и Chromium для локального запуска)
- Токен Telegram-бота от [@BotFather](https://t.me/BotFather)
- Каталог в Yandex Cloud с доступом к AI Studio:
  - API-ключ сервисного аккаунта
  - ID каталога (folder ID)
  - ID векторного хранилища (см. [База знаний](#-база-знаний))

---

## ⚙️ Переменные окружения

Создайте `.env` на основе `.env.example`:

```env
TELEGRAM_BOT_TOKEN=your_telegram_token

YANDEX_CLOUD_MODEL=yandexgpt/latest
YANDEX_CLOUD_FOLDER=your_folder_id
YANDEX_CLOUD_API_KEY=your_api_key
YANDEX_CLOUD_LLM_URL=https://rest-assistant.api.cloud.yandex.net/v1

VECTOR_STORE_ID=your_vector_store_id
```

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `YANDEX_CLOUD_MODEL` | Модель в формате URI без префикса, например `yandexgpt/latest`. Модель должна быть доступна в вашем каталоге |
| `YANDEX_CLOUD_FOLDER` | ID каталога Yandex Cloud |
| `YANDEX_CLOUD_API_KEY` | API-ключ сервисного аккаунта |
| `YANDEX_CLOUD_LLM_URL` | Базовый URL OpenAI-совместимого API Yandex AI Studio |
| `VECTOR_STORE_ID` | ID векторного хранилища с базой знаний |

> ⚠️ `.env` содержит секреты: не коммитьте его и не публикуйте логи с трейсбеками.

---

## 📚 База знаний

Исходные документы лежат в `docs/`. Чтобы создать векторное хранилище:

```bash
python scripts/create_vector_store.py
```

Скрипт:
1. загружает файлы из `docs/` (`.txt`, `.md`, `.pdf`, `.docx`) с явным MIME-типом;
2. создаёт хранилище с разбиением на фрагменты по 800 токенов (перекрытие 200);
3. ждёт индексации и проверяет, что **все файлы** проиндексированы (`file_counts`, а не только статус хранилища);
4. делает пробный поиск;
5. только при успехе записывает `VECTOR_STORE_ID` в `.env`.

Другую папку можно указать через `KB_DIR=путь python scripts/create_vector_store.py`.

Хранилище удаляется автоматически через **365 дней без использования** (`expires_after`). Если бот перестал находить выдержки, а API возвращает `404 not found`, хранилище, скорее всего, истекло, и его нужно пересоздать.

Старое хранилище после пересоздания не удаляется само: удалите его вручную (`scripts/deleting_of_old_database.py` или консоль Yandex Cloud).

---

## 🐳 Запуск через Docker

```bash
docker compose up -d --build
```

Логи:
```bash
docker compose logs -f
```

После изменения `.env` контейнер нужно перезапустить: переменные читаются при старте.

```bash
docker compose up -d
```

В образе используется **Chromium из Debian**. Он собран и под `amd64`, и под `arm64`, поэтому на Apple Silicon контейнер работает без эмуляции.

---

## 🧪 Локальный запуск (без Docker)

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

⚠️ Для парсинга каналов нужен установленный Chrome или Chromium. Локально chromedriver скачивается через `webdriver-manager`. Чтобы использовать системные, задайте `CHROME_BIN` и `CHROMEDRIVER_PATH`.

---

## 📊 Логи и статистика

- `logs/app.log`: журнал приложения, ротация каждый день, хранится 14 дней
- `logs/ai_logs/<месяц>_logs_<год>.json`: результаты всех анализов (текст, вывод, токены, время ответа, ошибка)
  - запись атомарная, поэтому при падении процесса файл не повреждается
  - повреждённый файл переименовывается в `*.broken-<дата>.json`, и начинается новый

Скрытая команда администратора:

```
/secret_admin_statistics_request
```

Возвращает за текущий месяц:
- количество запросов
- средние входные и выходные токены
- среднее время ответа
- JSON-файл со статистикой

---

## ⚠️ Ограничения и замечания

- **Парсинг каналов** выполняется через Selenium по публичной веб-версии `t.me/s/<канал>`: работают только публичные каналы. Частые запросы могут привести к ограничениям со стороны Telegram.
- Парсинг выполняется в **отдельном потоке**, поэтому бот продолжает отвечать другим пользователям. Одновременно запускается не больше 2 браузеров (`_PARSER_SEMAPHORE` в `app/bot/functions.py`), каждый занимает 200–500 МБ памяти.
- Качество ответа зависит от базы знаний: если нужной нормы нет в `docs/`, модель сообщит об этом в описании.
- Ответ модели **не является юридической консультацией**.