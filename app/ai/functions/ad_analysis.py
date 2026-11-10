import asyncio
import datetime
import json
import re
import time
from pathlib import Path
from typing import Final
from app.ai.client import client
from app.settings import settings, logger, MOSCOW_TZ
from app.ai.schemas import AiClientSendRequestResponse
from app.functions import load_data, save_data
from typing import Any
from app.database.functions.chunks import search
from app.database.schemas import SearchResult


GUIDED_JSON: Final[dict] = {
    "name": "ad_law_review",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "array",
                "description": "Список найденных нарушений. Если нарушений нет — один элемент с violations = \"Нет\"",
                "items": {
                    "type": "object",
                    "properties": {
                        "violations": {
                            "type": "string",
                            "enum": ["Да", "Нет"],
                            "title": "Violations",
                            "description": "Флаг наличия нарушения"
                        },
                        "description": {
                            "type": "string",
                            "title": "Description",
                            "description": "Объяснение с указанием статей"
                        },
                        "fine": {
                            "type": "integer",
                            "title": "Fine",
                            "description": "Максимальный штраф в рублях; 0, если нарушения нет"
                        },
                        "recommendation": {
                            "type": "string",
                            "title": "Recommendation",
                            "description": "Рекомендация с конкретным примером по устранению нарушения"
                        }
                    },
                    "required": ["violations", "description", "fine", "recommendation"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["analysis"],
        "additionalProperties": False
    }
}

SYSTEM_PROMPT: Final[str] = """\
Ты — эксперт по рекламному праву. В сообщении пользователя приведены выдержки из базы знаний
(законы, разъяснения ФАС и ЦБ) и текст запроса.

Порядок работы:
1. Сначала про себя оцени каждую выдержку: регулирует ли она именно ту ситуацию, о которой спрашивает
пользователь. Выдержка релевантна, только если содержит норму, которая прямо применима к запросу.
Общее совпадение темы (например, «реклама» вообще) не делает выдержку релевантной.
2. Нерелевантные выдержки полностью игнорируй: не упоминай их, не цитируй, не ссылайся на их статьи,
не используй их для выводов, штрафов и рекомендаций.
3. Делай анализ и ссылайся на статьи только по релевантным выдержкам.

Если ни одна выдержка не релевантна, верни ровно такой ответ и ничего больше:
{"analysis": [{"violations": "Нет", "description": "Релевантных статей в базе знаний не найдено.", "fine": 0,
"recommendation": "Обратитесь к юристу для проверки по иным нормам."}]}

Ответ возвращай строго как JSON-объект с единственным полем analysis — массивом объектов с полями:
- violations: "Да" или "Нет";
- description: строка с объяснением и указанием статей только из релевантных выдержек;
- fine: целое число — максимальный размер штрафа в рублях. Если штраф указан диапазоном,
возьми верхнюю границу. Если нарушения нет, укажи 0, никогда не null. Если нарушение установлено,
fine не может быть 0: возьми верхнюю границу санкции для юридического лица по применимой статье
КоАП РФ (для нарушений законодательства о рекламе — статья 14.3 КоАП РФ);
- recommendation: строка с рекомендацией и конкретным примером исправления.
Пример: {"analysis": [{"violations": "Нет", "description": "...", "fine": 0, "recommendation": "..."}]}
Не добавляй никаких других полей и не оборачивай ответ в markdown.
"""

# Дополнительные запросы к базе знаний: короткий рекламный текст сам по себе
# не вытягивает статьи о санкциях, поэтому добираем их отдельно.
AUX_QUERIES: Final[tuple[tuple[str, int, float], ...]] = (
    (
        "некорректное сравнение и недостоверные сведения в рекламе, общие требования "
        "к рекламе, статья 5 Федерального закона № 38-ФЗ «О рекламе»",
        4,
        0.50,
    ),
    (
        "штраф за нарушение законодательства о рекламе, статья 14.3 КоАП РФ, "
        "размер штрафа для юридических лиц",
        3,
        0.50,
    ),
)

async def _save_analysis_log(
    text: str,
    answers: list[dict],
    input_tokens: int,
    output_tokens: int,
    response_time_ms: float,
     error: str | None) -> None:
    """Пишет результат анализа в месячный JSON-лог. Никогда не бросает исключений."""
    try:
        violations_flag = any(
    answer["violations"] == "Да" or answer["fine"] > 0
    for answer in answers)
        sorted_answers = sorted(
    answers,
    key=lambda answer: answer["fine"],
     reverse=True)

        descriptions = ""
        recommendations = ""
        for i, answer in enumerate(sorted_answers, start=1):
            descriptions += f"{i}) Описание:\n{
    answer['description']}\n\nВозможный штраф: {
        answer['fine']}\n\n"
            recommendations += f"{i}) Рекомендация:\n{
    answer['recommendation']}\n\n"

        cell = {
            "Текст публикации": text,
            "Наличие нарушений": "Присутствуют 🚨" if violations_flag else "Отсутствуют ✅",
            "Описание": descriptions,
            "Рекомендации": recommendations,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "Время ответа в мс": response_time_ms,
            "Ошибка": error,
        }

        now = datetime.datetime.now(MOSCOW_TZ).replace(tzinfo=None)
        logs_dir = Path(settings.ai_logs_dir)
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_name = logs_dir / \
            f"{now.strftime('%B').lower()}_logs_{now.year}.json"

        try:
            data = await load_data(file_name)

        except json.JSONDecodeError:
            backup = file_name.with_suffix(f".broken-{now:%Y%m%d%H%M%S}.json")
            file_name.rename(backup)
            logger.error(
    f"Файл логов повреждён, сохранён как {backup}, начинаю новый")
            data = []

        if not isinstance(data, list):
            data = []

        data.append(cell)
        await save_data(file_name, data)
    except Exception as e:
        logger.exception(f"Не удалось записать лог анализа: {e}")

def _parse_fine(value: Any) -> int:
    """Максимальный штраф из значения модели.

    Модель может вернуть число, строку с диапазоном («от 100 000 до 500 000»)
    или null. Берём верхнюю границу: для диапазона — максимальное число.
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(int(value), 0)
    if isinstance(value, str):
        cleaned = (
            value.replace("\u00a0", " ")
            .replace("\u202f", " ")
            .replace(" ", "")
        )
        numbers = [int(number) for number in re.findall(r"\d+", cleaned)]
        return max(numbers) if numbers else 0
    return 0

def _normalize_answers(raw: Any) -> list[dict]:
    """Приводит ответ модели к списку словарей с гарантированными полями и типами."""
    if isinstance(raw, dict):
        raw = raw.get("analysis", [])
    if not isinstance(raw, list):
        return []

    answers = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        answers.append({
            "violations": "Да" if item.get("violations") == "Да" else "Нет",
            "description": str(item.get("description") or ""),
            "fine": _parse_fine(item.get("fine")),
            "recommendation": str(item.get("recommendation") or ""),
        })
    return answers

async def vector_database_law_search(text: str) -> str:
    """
    Находит выдержки из базы знаний и собирает их в контекст для промпта.
    При ошибке поиска возвращает пустую строку — анализ продолжается без контекста.
    """
    try:
        founded_chunks: list[SearchResult] = await asyncio.to_thread(
            search, text, 5, 0.35)
        for query, aux_top_k, aux_similarity in AUX_QUERIES:
            founded_chunks += await asyncio.to_thread(
                search, query, aux_top_k, aux_similarity)
    except Exception as e:
        logger.warning(
    f"Поиск по базе знаний не удался, анализ без контекста: {e}")
        return ""

    unique: list[SearchResult] = []
    seen: set[str] = set()
    for cell in founded_chunks:
        if cell.chunk.text in seen:
            continue
        seen.add(cell.chunk.text)
        unique.append(cell)

    logger.info(
    f"Найдено выдержек в базе знаний: {len(unique)} "
    f"(с учётом норм о рекламе и штрафах)")
    return "\n\n".join(
        f"[Выдержка {i}]\n{
            cell.chunk.text}"
        for i, cell in enumerate(unique, start=1)
    )

async def analyze_text(text: str, temperature: float = None) -> list[dict]:
    """
    Анализирует рекламный текст.

    Возвращает список нарушений (минимум один элемент при успехе).
    При любой ошибке возвращает пустой список — вызывающий код трактует это как ошибку.
    """
    start_time = time.perf_counter()
    input_tokens, output_tokens = 0, 0
    error: str | None = None

    try:
        knowledge_context = await vector_database_law_search(text)

        user_content = [
            {
                "type": "input_text",
                "text": (
                    f"Выдержки из базы знаний:\n\n{
    knowledge_context or 'Ничего не найдено.'}\n\n"
                    "---\n\n"
                    "Проанализируй рекламное утверждение: "
                    f"«{text}» "
                    "Определи нарушения рекламного законодательства и напиши рекомендации по их устранению."
                )
            }
        ]

        request_result: AiClientSendRequestResponse = await client.send_request(
            system_prompt=SYSTEM_PROMPT,
            guided_json=GUIDED_JSON,
            user_content=user_content,
            temperature=temperature,
        )
        answers = _normalize_answers(request_result.result)
        input_tokens = request_result.input_tokens or 0
        output_tokens = request_result.output_tokens or 0

        if not answers:
            error = f"Модель вернула пустой или некорректный analysis: {
    request_result.result!r}"
            logger.error(error)

    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        logger.exception(f"Ошибка при обработке запроса: {e}")
        answers = []

    response_time_ms = (time.perf_counter() - start_time) * 1000
    await _save_analysis_log(text, answers, input_tokens, output_tokens, response_time_ms, error)

    return answers

if __name__ == "__main__":
    async def main():
        single = await analyze_text(text="Наши конкуренты полное говно",
                                    temperature=0.0)
        print(single)
    asyncio.run(main())
