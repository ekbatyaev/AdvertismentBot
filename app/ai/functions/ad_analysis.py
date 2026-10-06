import asyncio
import datetime
import json
import time
from typing import Any
from typing import Final
from app.ai.client import client
from app.settings import settings, logger, MOSCOW_TZ
from app.ai.models import AiClientSendRequestResponse


GUIDED_JSON: Final[dict] = {
    "name": "ad_law_review",
    "strict": True,
    "schema": {
        "type": "array",
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
                    "description": "Максимальный штраф в рублях"
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
}

SYSTEM_PROMPT: Final[str] = """\
Ты — эксперт по рекламному праву. Используй подключённый поиск по базе знаний и обязательно опирайся на найденные выдержки. 
Ответ возвращай строго как JSON-массив объектов с полями violations (Да/Нет), description (строка), fine (целое число, максимальный размер штрафа в рублях) и recommendation (строка). 
Если штраф указан диапазоном, возьми верхнюю границу. Не добавляй никаких других полей."
"""

# Загрузка данных

async def load_data(data_file):
    try:
        with open(data_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return []


# Сохранение данных

async def save_data(data_file, data):
    with open(data_file, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


async def analyze_text(text: str, tools: list = None, temperature: float = None) -> list:

    user_content = \
        [
            {
                "type": "input_text",
                "text": (
                    "Проанализируй рекламное утверждение: "
                    f"«{text}» "
                    "Определи нарушения рекламного законодательства и напиши рекомендации по их устранению."
                )
            }
        ]

    flag_error = False
    analysis_of_texts = []
    input_tokens, output_tokens, response_time_ms  = 0, 0, 0
    try:
        start_time = time.perf_counter_ns()

        request_result: AiClientSendRequestResponse = await client.send_request(system_prompt = SYSTEM_PROMPT,
                                                           guided_json = GUIDED_JSON,
                                                           user_content = user_content,
                                                           tools = tools,
                                                           temperature = temperature)
        analysis_of_texts: list[dict, Any] = request_result.result
        input_tokens: int = request_result.input_tokens
        output_tokens: int = request_result.output_tokens

        logger.info(analysis_of_texts)
        end_time = time.perf_counter_ns()
        response_time_ms = (end_time - start_time) / 1_000_000

    except Exception as e:
        logger.error(f"Ошибка при обработке запроса", e)
        flag_error = True
        raise

    finally:
        if not flag_error:
            answer_list = analysis_of_texts
            violations_flag = any(answer["fine"] > 0 for answer in answer_list)
        else:
            answer_list = []
            violations_flag = False
        descriptions = ""
        recommendations = ""
        if violations_flag:
            answer_list = sorted(answer_list, key=lambda answer: answer["fine"], reverse=True)

        for i, answer in enumerate(answer_list):
            descriptions += f"{str(i + 1)}) Описание:\n" + answer[
                "description"] + "\n\nВозможный штраф: " + str(answer["fine"]) + "\n\n"
            recommendations += f"{str(i + 1)}) Рекомендация:\n" + answer["recommendation"] + "\n\n"

        cell = {
            "Текст публикации": text,
            "Наличие нарушений": "Присутствуют 🚨" if violations_flag == True else "Отсутствуют ✅",
            "Описание": descriptions,
            "Рекомендации": recommendations,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "Время ответа в мс": response_time_ms
        }

        now = datetime.datetime.now(MOSCOW_TZ).replace(tzinfo=None)
        month = now.strftime("%B").lower()
        file_name = str(f"{settings.ai_logs_dir}/{month}_logs_{now.year}.json")
        data = await load_data(file_name)
        data.append(cell)
        await save_data(file_name, data)

    return analysis_of_texts

if __name__ == "__main__":
    async def main():

        single = await analyze_text(text = "Наши конкуренты полное говно",
                                    tools = [{
                                                "searchIndex": {
                                                    "searchIndexIds": [settings.vector_store_id],
                                                    "maxNumResults": 10,
                                                    "callStrategy": {
                                                        "autoCall": {
                                                            "instruction": (
                                                                "Для каждого запроса обязательно выполняй поиск по базе знаний и используй результаты."
                                                            )
                                                        }
                                                    }
                                                }
                                            }
                                    ],
                                    temperature=0.0)
        print(single)
    asyncio.run(main())
