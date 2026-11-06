from app.ai.database.embedding_model import config
import numpy as np

def count_tokens(text: str) -> int:
    """Сколько токенов займёт текст в модели (включая служебные <s> и </s>)."""
    if config.counting_tokenizer is None:
        raise RuntimeError("Токенизатор не загружен, вызовите load_embedding_model()")
    return len(config.counting_tokenizer.encode(text).ids)

def count_tokens_batch(texts: list[str]) -> list[int]:
    """То же для списка текстов, быстрее чем по одному."""
    if config.counting_tokenizer is None:
        raise RuntimeError("Токенизатор не загружен, вызовите load_embedding_model()")
    return [len(e.ids) for e in config.counting_tokenizer.encode_batch(texts)]

def embed_texts(texts: list[str], batch_size: int = config.BATCH_SIZE) -> np.ndarray:
    """
    Векторизует список текстов.
    Возвращает массив shape (len(texts), embedding_dim), float32,
    каждый вектор нормализован (длина 1), поэтому сходство = скалярное произведение.
    """
    if config.model is None or config.tokenizer is None:
        raise RuntimeError("Embedding-модель не загружена, вызовите load_embedding_model()")
    if not texts:
        return np.empty((0, config.embedding_dim), dtype=np.float32)

    input_names = {i.name for i in config.model.get_inputs()}
    result = []

    for start in range(0, len(texts), batch_size):
        batch = config.tokenizer.encode_batch(texts[start:start + batch_size])

        inputs = {
            "input_ids": np.array([e.ids for e in batch], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in batch], dtype=np.int64),
        }
        if "token_type_ids" in input_names:
            inputs["token_type_ids"] = np.zeros_like(inputs["input_ids"])

        last_hidden_state = config.model.run(None, inputs)[0]   # (batch, seq_len, dim)
        vectors = last_hidden_state[:, 0]                # CLS-токен, как у bge-m3
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        result.append(vectors)

    return np.vstack(result).astype(np.float32)

def embed_text(text: str) -> np.ndarray:
    """Вектор одного текста, shape (embedding_dim,)."""
    return embed_texts([text])[0]
