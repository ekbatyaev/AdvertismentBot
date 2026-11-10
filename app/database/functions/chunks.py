from pathlib import Path
from app.database.embedding_model.functions import count_tokens, count_tokens_batch, embed_texts, embed_text
from app.database.embedding_model.config import MAX_TOKENS_LENGTH
from app.database.schemas import Chunk, SearchResult
from typing import Optional
from app.settings import logger, settings
import numpy as np
import re

DOCUMENT_DIVIDER = (r"(?=^# \[ТИП_ДОКУМЕНТА\]:|^Постановление Правительства Российской Федерации "
                    r"от|^РОССИЙСКАЯ ФЕДЕРАЦИЯ$)")
SECTION_DIVIDER = r"(?=^(?:Раздел|Глава|Статья) )"

chunks: list[Chunk] = []                 # все куски в памяти
matrix: Optional[np.ndarray] = None      # их векторы одной матрицей (n, 1024) для быстрого поиска

def clean_text(text: str) -> str:
    """Чистит пробельный мусор, сохраняя структуру (строки и абзацы)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")   # переносы Windows -> \n
    text = text.replace("\xa0", " ")                         # неразрывный пробел -> обычный
    text = re.sub(r"[ \t]+", " ", text)                      # табы и пробелы подряд -> один пробел
    text = re.sub(r" *\n *", "\n", text)                     # пробелы в начале и конце строк
    text = re.sub(r"\n{3,}", "\n\n", text)                   # больше одной пустой строки -> одна
    return text.strip()

async def fill_chunks_table(folder_path: Path) -> list[Chunk]:
    result: list[Chunk] = []
    for txt_file in folder_path.glob("*.txt"):
        text = clean_text(txt_file.read_text(encoding="utf-8"))

        # 1. Режем файл на отдельные документы (законы, письма, постановления)
        documents = [d.strip() for d in re.split(DOCUMENT_DIVIDER, text, flags=re.MULTILINE) if d.strip()]

        for document in documents:
            # Заголовок документа: строки "# [...]" или первая строка, если их нет
            title = ("\n".join(line for line in document.split("\n") if line.startswith("# [")) or
                     document.split("\n", 1)[0])

            # 2. Режем документ на разделы / главы / статьи
            parts = [p.strip() for p in re.split(SECTION_DIVIDER, document, flags=re.MULTILINE) if p.strip()]

            # 3. Короткий заголовок главы/раздела без статьи приклеиваем к следующему куску
            sections = []
            for part in parts:
                if sections and not sections[-1].startswith("Статья") and len(sections[-1]) < 300:
                    sections[-1] += "\n" + part
                else:
                    sections.append(part)

            # 4. Считаем токены всех кусков сразу (с заголовком документа — он тоже уйдёт в эмбеддинг)
            token_counts = count_tokens_batch([f"{title}\n{s}" for s in sections])

            # 5. Куски больше потолка делим пополам (сначала по строкам, потом по словам), пока не влезут
            fits = {s for s, n in zip(sections, token_counts) if n <= MAX_TOKENS_LENGTH}  # уже влезают —
            # не пересчитываем
            queue = sections[::-1]  # стек: первый кусок сверху
            chunks = []
            while queue:
                piece = queue.pop()
                if piece in fits or count_tokens(f"{title}\n{piece}") <= MAX_TOKENS_LENGTH:
                    chunks.append(f"{title}\n{piece}")
                    continue
                separator = "\n" if "\n" in piece else " "
                units = piece.split(separator)
                middle = len(units) // 2
                queue.append(separator.join(units[middle:]))   # вторая половина — ниже в стеке
                queue.append(separator.join(units[:middle]))   # первая половина — обработается первой

            # 6. Эмбеддинги всех кусков документа одним батчем (размерность 1024)
            embeddings = embed_texts(chunks)
            result += [Chunk(text=c, embedding=e) for c, e in zip(chunks, embeddings)]

    return result

def search(query: str, top_k: int = 5, similarity: float = 0.35) -> list[SearchResult]:
    scores = matrix @ embed_text(query)           # векторы нормализованы -> скалярное произведение=косинусное сходство
    best = np.argsort(scores)[::-1][:top_k]       # индексы top_k лучших по убыванию
    return [SearchResult(chunk=chunks[i], score=float(scores[i])) for i in best if scores[i] > similarity]

async def init_chunks(conn) -> None:
    global chunks, matrix
    # Создание таблицы чанков
    conn.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, text TEXT NOT NULL, "
                       "embedding BLOB NOT NULL)")

    # Таблица пустая — режем документы, считаем эмбеддинги и сохраняем
    if conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0:
        rows: list[Chunk] = await fill_chunks_table(settings.docs_dir)
        conn.executemany(
            "INSERT INTO chunks (text, embedding) VALUES (?, ?)",
            [(row.text, row.embedding.astype(np.float32).tobytes()) for row in rows],  # вектор -> байты
        )
        conn.commit()

    # Читаем всё обратно: байты -> вектор
    chunks = [
        Chunk(id=id_, text=text, embedding=np.frombuffer(blob, dtype=np.float32))
        for id_, text, blob in conn.execute("SELECT id, text, embedding FROM chunks")
    ]
    if not chunks:
        raise RuntimeError(
            f"База знаний пуста: в {settings.docs_dir} не найдено ни одного документа"
        )
    matrix = np.vstack([chunk.embedding for chunk in chunks])
    logger.info(f"База знаний загружена: {len(chunks)} чанков")
