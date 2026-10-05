"""Split Markdown documents into chunks for RAG.

Our 4 chunking rules:
1. Split at #, ##, ### headings (LangChain's MarkdownHeaderTextSplitter).
2. Keep each chunk under a token limit. A long section is split between
   blocks (paragraphs, tables, code blocks), and the next chunk repeats the
   last sentence of the previous one (overlap).
3. Never cut a table or code block in half. Only when one is too big on its
   own: a table is split by rows (header row repeated), code by lines.
4. Put a breadcrumb "[folder/file.md > H1 > H2 > H3]" on top of every chunk.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from langchain_text_splitters import MarkdownHeaderTextSplitter

TokenCounter = Callable[[str], int]

_HEADINGS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
_SPLITTER = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADINGS, strip_headers=True)

_FENCES = ("```", "~~~")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}")  # matches "| --- |" and "|:---:|"
_MAX_OVERLAP_TOKENS = 60


@dataclass(frozen=True)
class Block:
    kind: str  # "paragraph", "table" or "code"
    text: str


@dataclass(frozen=True)
class Chunk:
    text: str  # breadcrumb + body: this is what gets embedded and searched
    source: str  # e.g. "frontend/ui-label-mapping.md"
    breadcrumb: str
    index: int  # position of this chunk inside its file
    token_count: int


# ---------------------------------------------------------------------------
# Rule 1 + 4: split at headings, build the breadcrumb
# ---------------------------------------------------------------------------


def chunk_document(text: str, source: str, max_tokens: int, count_tokens: TokenCounter) -> list[Chunk]:
    """Split one Markdown file into chunks, each at most max_tokens long."""
    chunks: list[Chunk] = []
    for section in _SPLITTER.split_text(text):
        breadcrumb = _breadcrumb(source, section.metadata)
        header = f"[{breadcrumb}]"
        budget = max_tokens - count_tokens(header) - 1  # -1 for the newline
        for body in _section_bodies(parse_blocks(section.page_content), budget, count_tokens):
            full_text = f"{header}\n{body}"
            chunks.append(
                Chunk(
                    text=full_text,
                    source=source,
                    breadcrumb=breadcrumb,
                    index=len(chunks),
                    token_count=count_tokens(full_text),
                )
            )
    return chunks


def _breadcrumb(source: str, headings: dict) -> str:
    parts = [source, *(headings[key] for key in ("h1", "h2", "h3") if key in headings)]
    return " > ".join(parts)


# ---------------------------------------------------------------------------
# Rule 3: find paragraphs, tables and code blocks inside a section
# ---------------------------------------------------------------------------


def parse_blocks(text: str) -> list[Block]:
    """Turn the text of one section into paragraph, table and code blocks."""
    # LangChain marks a blank line between paragraphs as "  \n". Turn it back
    # into a real blank line so we can see where paragraphs end.
    lines = text.replace("  \n", "\n\n").split("\n")
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith(_FENCES):
            end = _code_end(lines, i)
            block = Block("code", "\n".join(lines[i : end + 1]).strip())
        elif stripped.startswith("|"):
            end = _run_end(lines, i, _is_table_line)
            block = Block("table", "\n".join(_shorten_separator(line) for line in lines[i : end + 1]).strip())
        else:
            end = _run_end(lines, i, _is_paragraph_line)
            block = Block("paragraph", "\n".join(lines[i : end + 1]).strip())
        blocks.append(block)
        i = end + 1
    return blocks


def _shorten_separator(line: str) -> str:
    """Turn "| --------------- | ---- |" into "| --- | --- |".

    Writers pad separator rows with long runs of dashes so the table lines up
    in a text editor. The tokenizer counts every dash as a token, which wastes
    hundreds of tokens per table, so we shorten them.
    """
    if _TABLE_SEPARATOR.match(line):
        return re.sub(r"-{3,}", "---", line)
    return line


def _code_end(lines: list[str], start: int) -> int:
    """Index of the closing fence (or the last line if it is never closed)."""
    fence = lines[start].strip()[:3]
    for j in range(start + 1, len(lines)):
        if lines[j].strip().startswith(fence):
            return j
    return len(lines) - 1


def _run_end(lines: list[str], start: int, belongs: Callable[[str], bool]) -> int:
    """Index of the last line in a run of lines that belong together."""
    end = start
    while end + 1 < len(lines) and belongs(lines[end + 1]):
        end += 1
    return end


def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")


def _is_paragraph_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith(("|", *_FENCES))


# ---------------------------------------------------------------------------
# Rule 2: keep chunks under the limit, with overlap
# ---------------------------------------------------------------------------


def _section_bodies(blocks: list[Block], budget: int, count: TokenCounter) -> list[str]:
    """Group a section's blocks into chunk bodies that each fit the budget."""
    pieces = [piece for block in blocks for piece in split_block(block, budget, count)]
    groups: list[list[Block]] = []
    current: list[Block] = []
    for piece in pieces:
        if current and count(_join([*current, piece])) > budget:
            groups.append(current)
            overlap = _overlap(current[-1], count)
            fits = overlap and count(_join([*overlap, piece])) <= budget
            current = [*overlap, piece] if fits else [piece]
        else:
            current = [*current, piece]
    if current:
        groups.append(current)
    return [_join(group) for group in groups]


def _join(blocks: list[Block]) -> str:
    return "\n\n".join(block.text for block in blocks)


def _overlap(last: Block, count: TokenCounter) -> list[Block]:
    """The last sentence of a paragraph, repeated at the start of the next chunk."""
    if last.kind != "paragraph":
        return []
    sentence = _SENTENCE_END.split(last.text)[-1]
    if count(sentence) > _MAX_OVERLAP_TOKENS:
        return []
    return [Block("paragraph", sentence)]


def split_block(block: Block, budget: int, count: TokenCounter) -> list[Block]:
    """Return the block as-is if it fits, otherwise cut it into smaller blocks."""
    if count(block.text) <= budget:
        return [block]
    if block.kind == "table":
        return _split_table(block, budget, count)
    if block.kind == "code":
        return _split_code(block, budget, count)
    return _split_paragraph(block, budget, count)


def _split_table(block: Block, budget: int, count: TokenCounter) -> list[Block]:
    """Split a big table by rows and repeat the header row in every piece."""
    lines = block.text.split("\n")
    has_header = len(lines) > 2 and _TABLE_SEPARATOR.match(lines[1]) is not None
    header, rows = (lines[:2], lines[2:]) if has_header else ([], lines)
    row_budget = max(budget - count("\n".join(header)), 1)
    return [Block("table", "\n".join([*header, group])) for group in _pack(rows, row_budget, count, "\n")]


def _split_code(block: Block, budget: int, count: TokenCounter) -> list[Block]:
    """Split a big code block by lines, keeping the ``` fences on every piece."""
    lines = block.text.split("\n")
    opening = lines[0]
    closed = len(lines) > 1 and lines[-1].strip().startswith(_FENCES)
    body = lines[1:-1] if closed else lines[1:]
    closing = lines[-1] if closed else opening.strip()[:3]
    line_budget = max(budget - count(f"{opening}\n{closing}"), 1)
    return [
        Block("code", f"{opening}\n{group}\n{closing}")
        for group in _pack(body, line_budget, count, "\n")
    ]


def _split_paragraph(block: Block, budget: int, count: TokenCounter) -> list[Block]:
    """Split a long paragraph by sentences."""
    sentences = _SENTENCE_END.split(block.text)
    return [Block("paragraph", group) for group in _pack(sentences, budget, count, " ")]


def _pack(parts: list[str], budget: int, count: TokenCounter, joiner: str) -> list[str]:
    """Put parts together in order, starting a new group when the budget is full.

    A part that is too big on its own (a huge table row, a very long line or
    sentence) is split by words first. This is the last resort, so no text is
    ever dropped.
    """
    fitting = [
        piece
        for part in parts
        for piece in (_greedy(part.split(), budget, count, " ") if count(part) > budget else [part])
    ]
    return _greedy(fitting, budget, count, joiner)


def _greedy(parts: list[str], budget: int, count: TokenCounter, joiner: str) -> list[str]:
    """Fill each group with as many parts as fit, then start the next group."""
    groups: list[str] = []
    current: list[str] = []
    for part in parts:
        if current and count(joiner.join([*current, part])) > budget:
            groups.append(joiner.join(current))
            current = [part]
        else:
            current = [*current, part]
    if current:
        groups.append(joiner.join(current))
    return groups
