from itertools import groupby
from pathlib import Path
from app.database.models.config import MAX_TOKENS_LENGTH
from app.database.models.functions import count_tokens_batch, embed_texts, count_tokens
from app.database.schemas import Chunk
from app.database.functions.chunks.schemas import LegalBlock
import re


DOCUMENT_DIVIDER = (
    r"(?=^# \[ТИП_ДОКУМЕНТА\]:|^Постановление Правительства Российской Федерации "
    r"от|^РОССИЙСКАЯ ФЕДЕРАЦИЯ$)"
)
SECTION_DIVIDER = r"(?=^(?:Раздел|Глава|Статья) )"
CHAPTER_RE = re.compile(r"^(?:Раздел|Глава)\s+")


PART_RE = re.compile(r"^\d+(?:\.\d+)*\.\s+")
POINT_RE = re.compile(r"^\d+\)\s+")
SUBPOINT_RE = re.compile(r"^[а-яё]\)\s+")


TARGET_TOKENS = min(280, MAX_TOKENS_LENGTH)
MAX_CHUNK_TOKENS = min(450, MAX_TOKENS_LENGTH)


def split_long_block(text, render, target=TARGET_TOKENS, limit=MAX_CHUNK_TOKENS, level=0):
    """Аварийное деление: абзацы → предложения → слова с бинарным поиском."""
    target = min(limit, max(target, count_tokens(render("")) + 1))
    if count_tokens(render(text)) <= target:
        return [text]

    if level < 2:
        if level == 0:
            units, separator = re.split(r"\n{2,}", text), "\n\n"
        else:
            # Не отрываем номер части: «5. Текст…».
            units = re.split(r"(?<!\d\.)(?<=[.!?])\s+(?=[А-ЯЁA-Z0-9\"«(])", text)
            separator = " "
        if len(units) == 1:
            return split_long_block(text, render, target, limit, level + 1)

        pieces, current = [], ""
        for unit in units:
            if count_tokens(render(unit)) > target:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.extend(split_long_block(unit, render, target, limit, level + 1))
            else:
                candidate = unit if not current else current + separator + unit
                if current and count_tokens(render(candidate)) > target:
                    pieces.append(current)
                    current = unit
                else:
                    current = candidate
        if current:
            pieces.append(current)
        return pieces

    words, pieces, start = text.split(), [], 0
    while start < len(words):
        low, high, best = start + 1, len(words), None
        while low <= high:
            middle = (low + high) // 2
            candidate = " ".join(words[start:middle])
            if count_tokens(render(candidate)) <= target:
                best, low = middle, middle + 1
            else:
                high = middle - 1
        if best is None:
            raise ValueError(f"Контекст или слово не влезает в чанк: {render('')[:500]!r}")
        pieces.append(" ".join(words[start:best]))
        start = best

    # Не оставляем последний хвост из нескольких слов.
    if len(pieces) >= 2 and count_tokens(render(pieces[-1])) < max(32, target // 4):
        combined = (pieces[-2] + " " + pieces[-1]).split()
        middle = len(combined) // 2
        for i in sorted(range(1, len(combined)), key=lambda x: abs(x - middle)):
            previous, last = " ".join(combined[:i]), " ".join(combined[i:])
            if count_tokens(render(previous)) <= target and count_tokens(render(last)) <= target:
                pieces[-2:] = [previous, last]
                break
    return pieces


def pack_blocks(blocks: list[LegalBlock]) -> list[str]:
    """Добавляет контекст и объединяет соседние пункты до целевого размера."""
    def render(block, text):
        context = block.context
        header = "\n".join(
            x for x in [block.document_title, block.article_title, *context] if x
        )
        if count_tokens(header) > MAX_CHUNK_TOKENS // 2:
            context = tuple(
                item if len(item) <= 280 else item[:280].rsplit(" ", 1)[0].rstrip() + " …"
                for item in context
            )
        while context:
            header = "\n".join(
                x for x in [block.document_title, block.article_title, *context] if x
            )
            if count_tokens(header) <= MAX_CHUNK_TOKENS - 32:
                break
            context = context[1:]
        return "\n".join(
            x for x in [block.document_title, block.article_title, *context, text] if x
        ).strip()

    def emit(group):
        rendered = render(group[0], "\n".join(block.text for block in group))
        if count_tokens(rendered) <= TARGET_TOKENS:
            return [rendered]
        if len(group) > 1:
            return [chunk for block in group for chunk in emit([block])]
        block = group[0]
        render_block = lambda text: render(block, text)
        return [render(block, text) for text in split_long_block(block.text, render_block)]

    chunks = []
    key = lambda block: (block.document_title, block.article_title, block.context)
    for _, group_iterator in groupby(blocks, key=key):
        current = []
        for block in group_iterator:
            candidate = current + [block]
            rendered = render(candidate[0], "\n".join(x.text for x in candidate))
            if current and count_tokens(rendered) > TARGET_TOKENS:
                chunks.extend(emit(current))
                current = [block]
            else:
                current = candidate
        if current:
            chunks.extend(emit(current))
    return chunks


def split_article(section: str, document_title: str) -> list[LegalBlock]:
    """Разбирает статью в дерево и передаёт родительские нормы в листья."""
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    article_index = next(
        (i for i, line in enumerate(lines) if re.match(r"^Статья\s+", line)), None
    )
    if article_index is not None:
        article_title = "\n".join(lines[:article_index + 1])
        lines = lines[article_index + 1:]
    elif lines and CHAPTER_RE.match(lines[0]):
        article_title, lines = lines[0], lines[1:]
    else:
        article_title = ""

    # Узел: [текст, уровень, дети]. Уровни: часть 0, пункт 1, подпункт 2, текст 3.
    root = ["", -1, []]
    stack, last_node = [root], None
    for line in lines:
        if line.startswith(("(", "[")) and last_node is not None:
            last_node[0] += "\n" + line
            continue
        if PART_RE.match(line):
            level = 0
        elif POINT_RE.match(line):
            level = 1
        elif SUBPOINT_RE.match(line):
            level = 2
        else:
            level = 3
        while stack[-1][1] >= level:
            stack.pop()
        node = [line, level, []]
        stack[-1][2].append(node)
        last_node = node
        if level < 3:
            stack.append(node)

    blocks = []

    def visit(node, ancestors):
        if node[2]:
            for child in node[2]:
                visit(child, ancestors + ((node[0],) if node[0] else ()))
        elif node[0]:
            blocks.append(LegalBlock(text=node[0], document_title=document_title, article_title=article_title,
                                     context=ancestors))

    for child in root[2]:
        visit(child, ())
    return blocks


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def fill_chunks_table(folder_path: Path) -> list[Chunk]:
    result = []
    for txt_file in sorted(folder_path.glob("*.txt")):
        text = clean_text(txt_file.read_text(encoding="utf-8"))
        documents = [d.strip() for d in re.split(DOCUMENT_DIVIDER, text, flags=re.MULTILINE) if d.strip()]
        raw_title = ""

        for document in documents:
            lines = [x.strip() for x in document.splitlines() if x.strip() and x.strip() != "---"]
            metadata = [x for x in lines if x.startswith("# [")]
            if metadata:
                document_title = "\n".join(metadata)
                body = [x for x in lines if not x.startswith("# [")]
            elif lines and lines[0] == "РОССИЙСКАЯ ФЕДЕРАЦИЯ":
                if len(lines) >= 3 and lines[1] == "ФЕДЕРАЛЬНЫЙ ЗАКОН":
                    raw_title = "\n".join(lines[:3])
                    document_title, body = raw_title, lines[3:]
                else:
                    document_title, body = raw_title or lines[0], lines[1:]
            elif lines:
                document_title, body = lines[0], lines[1:]
            else:
                continue

            parts = [p.strip() for p in re.split(SECTION_DIVIDER, "\n".join(body), flags=re.MULTILINE) if p.strip()]
            sections = []
            for part in parts:
                if sections and CHAPTER_RE.match(sections[-1]) and len(sections[-1]) < 300:
                    sections[-1] += "\n" + part
                else:
                    sections.append(part)

            blocks = [block for section in sections for block in split_article(section, document_title)]
            document_chunks = pack_blocks(blocks)
            for chunk_text, token_count in zip(document_chunks, count_tokens_batch(document_chunks)):
                if token_count > MAX_CHUNK_TOKENS:
                    raise ValueError(f"Чанк {token_count} > {MAX_CHUNK_TOKENS}: {chunk_text[:160]!r}")

            embeddings = embed_texts(document_chunks)
            result.extend(Chunk(text=text, embedding=embedding) for text, embedding in zip(document_chunks, embeddings))
    return result
