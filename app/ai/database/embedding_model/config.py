from app.settings import settings, logger
from typing import Optional
import onnxruntime as ort
from tokenizers import Tokenizer

model: Optional[ort.InferenceSession] = None
tokenizer: Optional[Tokenizer] = None
counting_tokenizer: Optional[Tokenizer] = None
embedding_dim: Optional[int] = None

MAX_TOKENS_LENGTH = 1024
BATCH_SIZE = 10

def load_embedding_model() -> None:
    """Блокирующая загрузка embedding-модели (диск/CPU)."""
    global model, tokenizer, embedding_dim, counting_tokenizer

    if model is not None:
        return

    model_path = settings.embedding_model_dir / "model_quantized.onnx"
    tokenizer_path = settings.embedding_model_dir / "tokenizer.json"

    if not model_path.is_file():
        raise FileNotFoundError(f"Embedding-модель не найдена: {model_path}")
    if not tokenizer_path.is_file():
        raise FileNotFoundError(f"Токенизатор не найден: {tokenizer_path}")

    logger.info("Загрузка embedding-модели: %s", model_path)
    model = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    counting_tokenizer = Tokenizer.from_file(str(tokenizer_path))

    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.enable_truncation(MAX_TOKENS_LENGTH)
    pad_id = tokenizer.token_to_id("<pad>")
    tokenizer.enable_padding(pad_id=pad_id if pad_id is not None else 1, pad_token="<pad>")

    embedding_dim = model.get_outputs()[0].shape[-1]
    if not isinstance(embedding_dim, int):
        raise RuntimeError("Не удалось определить размерность embedding-модели")
    logger.info("Embedding-модель загружена. Размерность: %d", embedding_dim)