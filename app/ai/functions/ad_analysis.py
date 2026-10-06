import asyncio
import datetime
import json
import re
import time
from typing import Any, List, Dict
from zoneinfo import ZoneInfo
from openai import AsyncOpenAI
from typing import Final
from app.ai.client import client


JSON_SCHEMA: Final[dict] = {
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

def extract_json_text(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("\n", 1)[0]
    return cleaned.strip()


def normalize_fine_field(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for item in data:
        fine_value = item.get("fine")
        if isinstance(fine_value, str):
            numbers = re.findall(r"\d+", fine_value.replace(" ", ""))
            if numbers:
                item["fine"] = int(numbers[-1])
            else:
                item["fine"] = 0
    return data


async def analyze_text(text: str, tools: list = None, temperature: float = None) -> Dict:
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

    try:
        fields: Dict[str, Any] = await client.send_request(system_prompt=SYSTEM_PROMPT,
                                                           user_content=user_content, guided_json=GUIDED_JSON)
        logger.info(fields)

    except Exception as e:
        logger.error(f"Ошибка при обработке запроса", e)
        raise
    return fields

    if not all([api_key, folder_id, vector_store_id]):
        print(
            "Убедитесь, что в .env заданы YANDEX_CLOUD_API_KEY, YANDEX_CLOUD_FOLDER и VECTOR_STORE_ID."
        )
        return {"model_answer": "Убедитесь, что в .env заданы YANDEX_CLOUD_API_KEY, YANDEX_CLOUD_FOLDER и VECTOR_STORE_ID.", "error": True }

    start_time = time.perf_counter_ns()

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://rest-assistant.api.cloud.yandex.net/v1",
        project=folder_id,
        timeout=120,
    )

    response = await client.responses.create(
        model=f"gpt://{folder_id}/{model_alias}",
        instructions=(
            "Ты — эксперт по рекламному праву. Используй подключённый поиск по базе знаний "
            "и обязательно опирайся на найденные выдержки. "
            "Ответ возвращай строго как JSON-массив объектов с полями violations (Да/Нет), "
            "description (строка), fine (целое число, максимальный размер штрафа в рублях) и recommendation (строка)."
            "Если штраф указан диапазоном, возьми верхнюю границу. Не добавляй никаких других полей."
        ),
        tools=[
            {
                "searchIndex": {
                    "searchIndexIds": [vector_store_id],
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
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Проанализируй рекламное утверждение: "
                            f"«{message}» "
                            "Определи нарушения рекламного законодательства и напиши рекомендации по их устранению."
                        )
                    }
                ],
            }
        ],
        extra_body={
            "json_schema": JSON_SCHEMA,
        },
    )
    end_time = time.perf_counter_ns()
    response_time_ms = (end_time - start_time) / 1_000_000
    raw_output = response.output_text or ""
    json_text = extract_json_text(raw_output)
    flag_error = False
    parsed = ""
    try:
        parsed = json.loads(json_text)
        if isinstance(parsed, list):
            parsed = normalize_fine_field(parsed)
        return {"model_answer": json.dumps(parsed, indent=2, ensure_ascii=False), "error": flag_error}

    except json.JSONDecodeError as error:
        flag_error = True
        return {"model_answer": f"Полученный ответ не соответствует JSON-схеме: {error}\nТекст ответа:\n{json_text}",
                "error": flag_error}
    finally:

        if not flag_error:
            answer_list = parsed
            violations_flag = any(answer["fine"] > 0 for answer in answer_list)
        else:
            answer_list = []
            violations_flag = False
        input_tokens, output_tokens = response.usage.input_tokens, response.usage.output_tokens
        descriptions = ""
        recommendations = ""
        if violations_flag:
            answer_list = sorted(answer_list, key=lambda answer: answer["fine"], reverse=True)

        for i, answer in enumerate(answer_list):
            descriptions += f"{str(i + 1)}) Описание:\n" + answer[
                "description"] + "\n\nВозможный штраф: " + str(answer["fine"]) + "\n\n"
            recommendations += f"{str(i + 1)}) Рекомендация:\n" + answer["recommendation"] + "\n\n"

        cell = {
            "Текст публикации": message,
            "Наличие нарушений": "Присутствуют 🚨" if violations_flag == True else "Отсутствуют ✅",
            "Описание": descriptions,
            "Рекомендации": recommendations,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "Время ответа в мс": response_time_ms
        }

        now = datetime.datetime.now(ZoneInfo("Europe/Moscow"))
        month = now.strftime("%B").lower()
        file_name = f"logs/{month}_logs_{now.year}.json"
        data = await load_data(file_name)
        data.append(cell)
        await save_data(file_name, data)

if __name__ == "__main__":
    async def main():
        results = await asyncio.gather(
            get_model_analysis("A"),
            get_model_analysis("B"),
            get_model_analysis("C"),
        )

        for i, result in enumerate(results, 1):
            print(f"\n=== RESULT {i} ===")
            print(result)

        single = await get_model_analysis("Наши конкуренты полное говно")
        print("\n=== SINGLE ===")
        print(single)
    asyncio.run(main())
