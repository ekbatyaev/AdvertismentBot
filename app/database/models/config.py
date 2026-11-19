from app.settings import settings, logger
from typing import Optional
import onnxruntime as ort
from tokenizers import Tokenizer


# Глобавльные переменные эмбеддинг модели
embedding_model: Optional[ort.InferenceSession] = None
embedding_tokenizer: Optional[Tokenizer] = None
embedding_counting_tokenizer: Optional[Tokenizer] = None
embedding_dim: Optional[int] = None
EMBEDDING_BATCH_SIZE = 10

MAX_TOKENS_LENGTH = 1024


# Глобальные переменные реранкинг модели
reranker_model: Optional[ort.InferenceSession] = None
reranker_tokenizer: Optional[Tokenizer] = None
reranker_input_names = None


def load_embedding_model() -> None:
    """Блокирующая загрузка embedding-модели (диск/CPU)."""
    global embedding_model, embedding_tokenizer, \
        embedding_dim, embedding_counting_tokenizer

    if embedding_model is not None:
        return

    model_path = settings.embedding_model_dir / "model_quantized.onnx"
    tokenizer_path = settings.embedding_model_dir / "tokenizer.json"

    if not model_path.is_file():
        raise FileNotFoundError(f"Embedding-модель не найдена: {model_path}")
    if not tokenizer_path.is_file():
        raise FileNotFoundError(f"Токенизатор не найден: {tokenizer_path}")

    logger.info(f"Загрузка embedding-модели: {model_path}")
    embedding_model = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    embedding_counting_tokenizer = Tokenizer.from_file(str(tokenizer_path))

    embedding_tokenizer = Tokenizer.from_file(str(tokenizer_path))
    embedding_tokenizer.enable_truncation(MAX_TOKENS_LENGTH)
    pad_id = embedding_tokenizer.token_to_id("<pad>")
    embedding_tokenizer.enable_padding(pad_id=pad_id if pad_id is not None else 1, pad_token="<pad>")

    embedding_dim = embedding_model.get_outputs()[0].shape[-1]
    if not isinstance(embedding_dim, int):
        raise RuntimeError("Не удалось определить размерность embedding-модели")
    logger.info(f"Embedding-модель загружена. Размерность: {embedding_dim}")


def load_reranker_model() -> None:
    """Вызывать один раз при старте приложения."""
    global reranker_model, reranker_tokenizer, reranker_input_names

    model_path = settings.reranker_model_dir / "model_quantized.onnx"
    tokenizer_path = settings.reranker_model_dir / "tokenizer.json"

    reranker_tokenizer = Tokenizer.from_file(str(tokenizer_path))

    reranker_tokenizer.enable_truncation(max_length=MAX_TOKENS_LENGTH)
    reranker_tokenizer.enable_padding()

    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1

    reranker_model = ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )

    reranker_input_names = {
        item.name
        for item in reranker_model.get_inputs()
    }


def load_models() -> None:
    load_embedding_model()
    load_reranker_model()
