import numpy as np
from app.database.models.functions import embed_text, rerank_results
from app.database.schemas import Chunk, SearchResult
from app.settings import settings, logger
from app.database.functions.chunks.fill import fill_chunks_table


def search(query: str, top_k: int = 5, count_rerank: int = 20, similarity: float = 0.35) -> list[SearchResult]:
    emb_scores = matrix @ embed_text(query)           # векторы нормализованы -> скалярное произведение=косинусное сходство
    emb_sorted = np.argsort(emb_scores)[::-1][:count_rerank]     # индексы top_k лучших по убыванию

    # Сортируем по значению эмбеддинга
    emb_best = [i for i in emb_sorted if emb_scores[i] > similarity]

    # Используем для сортировки реранкер
    ranked = rerank_results(query, chunks, emb_best)[:top_k]

    return [SearchResult(chunk=chunks[idx], score=score) for idx, score in ranked]


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
