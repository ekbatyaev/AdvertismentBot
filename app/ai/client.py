import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Optional
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, OpenAIError
from app.ai.models import AiClientSendRequestResponse
from app.settings import settings, logger


class LLMClientError(Exception):
    """Базовое исключение клиента."""


class LLMRequestError(LLMClientError):
    """Не удалось получить корректный ответ после всех попыток."""


class LLMResponseParseError(LLMClientError):
    """Ответ модели пришёл, но его не удалось распарсить в ожидаемый формат."""


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _extract_json(content: str) -> Any:
    """
    Достаёт JSON из ответа модели, даже если он обёрнут в markdown-разметку
    (```json ... ```) или окружён лишним текстом.
    """
    cleaned = content.strip()

    cleaned = _CODE_FENCE_RE.sub("", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            raise LLMResponseParseError(
                f"Не удалось распарсить content как JSON: {content!r}"
            ) from e

    raise LLMResponseParseError(f"Не удалось распарсить content как JSON: {content!r}")


@dataclass
class LLMClient:
    api_key: str = settings.yandex_cloud_api_key
    api_base: str = settings.yandex_cloud_llm_url or "https://rest-assistant.api.cloud.yandex.net/v1"
    model_name: str = settings.yandex_cloud_model or "aliceai-llm"
    folder_id: Optional[str] = settings.yandex_cloud_folder or None
    vector_store_id: Optional[str] = settings.vector_store_id or None
    max_tokens: int = 30000
    temperature: float = 0.8
    request_timeout: float = 100.0
    max_retries: int = 3
    system_prompt: str = ""

    async def send_request(
        self,
        user_content: Any,
        guided_json: Optional[dict] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[int] = None,
        tools: Optional[list] = None
    ) -> AiClientSendRequestResponse:
        """
        Отправляет запрос в LLM (Yandex Cloud, Responses API) с retry-логикой
        и обработкой ошибок.

        user_content: строка или список content-блоков (input_text/input_image и т.д.)
        guided_json: JSON-схема для structured output (опционально)
        system_prompt: переопределить системный промпт по умолчанию (опционально)

        Возвращает распарсенный JSON-объект из output_text ответа модели.
        """

        extra_body = {}
        if guided_json is not None:
            extra_body["json_schema"] = guided_json

        last_error: Optional[Exception] = None

        async with AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
            project=self.folder_id,
            timeout=self.request_timeout,
        ) as async_http_client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await async_http_client.responses.create(
                        model=f"gpt://{self.folder_id}/{self.model_name}",
                        instructions=system_prompt,
                        max_output_tokens=self.max_tokens,
                        temperature=temperature or self.temperature,
                        tools = tools,
                        input=[
                            {
                                "role": "user",
                                "content": user_content,
                            }
                        ],
                        extra_body=extra_body,
                        stream=False
                    )

                    raw_output = response.output_text or ""

                    result = _extract_json(raw_output)
                    return AiClientSendRequestResponse(result = result,
                                                       input_tokens = response.usage.input_tokens,
                                                       output_tokens = response.usage.output_tokens)

                except APITimeoutError as e:
                    last_error = e
                    logger.warning("Таймаут на попытке %s/%s", attempt, self.max_retries)

                except (APIConnectionError, OpenAIError) as e:
                    last_error = e
                    logger.warning(
                        "Ошибка запроса на попытке %s/%s: %s", attempt, self.max_retries, e
                    )

                except LLMResponseParseError as e:
                    last_error = e
                    logger.warning(
                        "Ошибка парсинга ответа на попытке %s/%s: %s",
                        attempt,
                        self.max_retries,
                        e,
                    )

        raise LLMRequestError(
            f"Превышено количество попыток ({self.max_retries})"
        ) from last_error


client = LLMClient()

if __name__ == "__main__":

    async def _main() -> None:
        result = await client.send_request(
            user_content=[{"type": "input_text", "text": "Верни JSON с полем code = 'print(1)'"}],
            guided_json={
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
                "additionalProperties": False,
            }
        )
        print(result)

    asyncio.run(_main())