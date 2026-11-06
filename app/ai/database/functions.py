from pathlib import Path
from app.ai.database.embedding_model.functions import count_tokens, count_tokens_batch, embed_texts
from app.ai.database.embedding_model.config import MAX_TOKENS_LENGTH
from app.ai.database.schemas import Chunk
import re

DOCUMENT_DIVIDER = r"(?=^# \[ТИП_ДОКУМЕНТА\]:|^Постановление Правительства Российской Федерации от|^РОССИЙСКАЯ ФЕДЕРАЦИЯ$)"
SECTION_DIVIDER = r"(?=^(?:Раздел|Глава|Статья) )"


def clean_text(text: str) -> str:
    """Чистит пробельный мусор, сохраняя структуру (строки и абзацы)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")   # переносы Windows -> \n
    text = text.replace("\xa0", " ")                         # неразрывный пробел -> обычный
    text = re.sub(r"[ \t]+", " ", text)                      # табы и пробелы подряд -> один пробел
    text = re.sub(r" *\n *", "\n", text)                     # пробелы в начале и конце строк
    text = re.sub(r"\n{3,}", "\n\n", text)                   # больше одной пустой строки -> одна
    return text.strip()


async def fill_database(folder_path: Path) -> list[Chunk]:
    result: list[Chunk] = []
    for txt_file in folder_path.glob("*.txt"):
        text = clean_text(txt_file.read_text(encoding="utf-8"))

        # 1. Режем файл на отдельные документы (законы, письма, постановления)
        documents = [d.strip() for d in re.split(DOCUMENT_DIVIDER, text, flags=re.MULTILINE) if d.strip()]

        for document in documents:
            # Заголовок документа: строки "# [...]" или первая строка, если их нет
            title = "\n".join(line for line in document.split("\n") if line.startswith("# [")) or document.split("\n", 1)[0]

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
            fits = {s for s, n in zip(sections, token_counts) if n <= MAX_TOKENS_LENGTH}   # уже влезают — не пересчитываем
            queue = sections[::-1]                                                  # стек: первый кусок сверху
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