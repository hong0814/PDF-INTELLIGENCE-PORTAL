from __future__ import annotations

import asyncio
import random
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from bs4 import BeautifulSoup

from pdftablesearch.config import get_settings
from pdftablesearch.llm_client import ZaiLLMClient
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

_settings = get_settings()

_STYLE_INJECT = """<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 40px; color: #1a1a1a; line-height: 1.7; }
h1 { font-size: 1.8em; border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-top: 32px; }
h2 { font-size: 1.3em; color: #2563eb; margin-top: 28px; }
h3 { font-size: 1.1em; color: #374151; }
table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.9em; }
th { background: #f0f4ff; color: #1e40af; font-weight: 600; text-align: left; padding: 8px 12px; border: 1px solid #d1d5db; }
td { padding: 6px 12px; border: 1px solid #d1d5db; }
tr:nth-child(even) td { background: #f9fafb; }
p { margin: 8px 0; }
</style>"""

_SKIP_TAGS = frozenset(
    ("script", "style", "head", "meta", "link", "title", "noscript")
)

_SEP_PATTERN = re.compile(
    r"<div[^>]*class=['\"][^'\"]*page-sep[^'\"]*['\"]"
    r"[^>]*data-pn=['\"](\d+)['\"][^>]*>",
    re.IGNORECASE,
)

def _build_translate_prompt(src: str, tgt: str) -> str:
    return (
        f"You are a professional translator. Translate each text block from {src} to {tgt}.\n"
        "Rules:\n"
        "- Keep the ###N### markers exactly as-is. Translate ONLY the text after each marker.\n"
        f"- Translate every word from {src} to {tgt}. Do not leave any untranslated text.\n"
        "- Do NOT translate numbers, percentages, dates, or currency symbols.\n"
        "- For company names, translate to their official name in the target language.\n"
        "- Return ALL items in the same order with ###N### markers.\n"
        "- No explanation or extra text.\n"
    )

# Delimiter that won't appear in natural text
_DELIM = "###"

# Maximum concurrent translation API calls
# Reduced to 1 (sequential) to avoid 429 rate limits on translation API
_MAX_CONCURRENT = 1

_INTER_PAGE_DELAY = 3

_BATCH_SIZE = 10

_TRANSLATION_TIMEOUT = 60
_DEFAULT_MODEL = _settings.zai_llm_model


# ---------------------------------------------------------------------------
# Page splitting
# ---------------------------------------------------------------------------

def split_html_by_pages(html_content: str) -> list[tuple[int, str]]:
    """Split HTML into (page_number, html_chunk) tuples using page-sep markers.

    If no separators are found the entire document is returned as page 1.
    """
    matches = list(_SEP_PATTERN.finditer(html_content))

    if not matches:
        return [(1, html_content)]

    pages: list[tuple[int, str]] = []

    for i, match in enumerate(matches):
        page_num = int(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html_content)
        pages.append((page_num, html_content[start:end]))

    return pages


# ---------------------------------------------------------------------------
# Core: extract texts → 1 API call → replace back
# ---------------------------------------------------------------------------

def _translate_page(
    page_html: str,
    client: ZaiLLMClient,
    src_name: str,
    tgt_name: str,
) -> str:
    """Translate a page by extracting texts, translating in one call, mapping back."""
    soup = BeautifulSoup(page_html, "html.parser")

    # 1. Collect all visible text nodes
    text_nodes = [
        node
        for node in soup.find_all(string=True)
        if node.parent.name not in _SKIP_TAGS and node.strip()
    ]

    if not text_nodes:
        return _clean_attrs_str(str(soup))

    _HANGUL = re.compile(r"[가-힣]")
    _LATIN = re.compile(r"[a-zA-Z]")
    _src_re = _HANGUL if ("한국" in src_name or src_name.lower() in ("ko", "korean")) else _LATIN

    unique_texts: list[str] = []
    seen: set[str] = set()
    for node in text_nodes:
        key = node.strip()
        if key not in seen and _src_re.search(key):
            seen.add(key)
            unique_texts.append(key)

    if not unique_texts:
        return _clean_attrs_str(str(soup))

    # 3. Translate in batches — partial failures OK
    cache: dict[str, str] = {}
    for batch_start in range(0, len(unique_texts), _BATCH_SIZE):
        batch = unique_texts[batch_start:batch_start + _BATCH_SIZE]
        try:
            batch_cache = _translate_all_in_one(batch, client, src_name, tgt_name)
            cache.update(batch_cache)
        except Exception as exc:
            logger.warning("Batch %d-%d failed: %s, keeping originals", batch_start, batch_start + len(batch), exc)
        if batch_start + _BATCH_SIZE < len(unique_texts):
            time.sleep(1)

    # 4. Replace texts in the soup tree
    for node in text_nodes:
        original = node.strip()
        translated = cache.get(original, original)
        leading = node[: len(node) - len(node.lstrip())]
        trailing = node[len(node.rstrip()) :]
        node.replace_with(leading + translated + trailing)

    return _clean_attrs_str(str(soup))


def _translate_all_in_one(
    texts: list[str],
    client: ZaiLLMClient,
    src_name: str,
    tgt_name: str,
) -> dict[str, str]:
    """Send all texts in one API call with ###N### delimiter format."""
    prompt = _build_translate_prompt(src_name, tgt_name)

    # Build input with ###N### markers
    parts = []
    for i, t in enumerate(texts):
        parts.append(f"{_DELIM}{i+1}{_DELIM}\n{t}")
    user_content = "\n".join(parts)

    for attempt in range(5):
        try:
            response = client._llm.invoke([
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ])
            raw = response.content.strip()
            cache = _parse_delimited_response(raw, texts)
            if len(cache) >= len(texts) * 0.5:
                return cache
            logger.warning(
                "Translation parse returned %d/%d items, retrying (attempt %d)",
                len(cache), len(texts), attempt + 1,
            )
        except Exception as exc:
            is_rate_limit = "429" in str(exc) or "rate" in str(exc).lower()
            base = 30 if is_rate_limit else 5
            wait = min(base * (2 ** attempt) + random.uniform(0, 10), 300)
            logger.warning(
                "Translation API error (attempt %d/5): %s — waiting %.0fs",
                attempt + 1, exc, wait,
            )
            time.sleep(wait)

    logger.error("All translation attempts failed for %d texts", len(texts))
    return {t: t for t in texts}


_DELIM_RE = re.compile(r"###(\d+)###\s*\n", re.MULTILINE)


def _parse_delimited_response(
    raw: str,
    original_texts: list[str],
) -> dict[str, str]:
    """Parse ###N### delimited response into {original: translated}."""
    cache: dict[str, str] = {}

    parts = _DELIM_RE.split(raw)
    # After split: ['', '1', 'body', '2', 'body', ...]

    i = 1
    while i + 1 < len(parts):
        try:
            num = int(parts[i].strip())
        except ValueError:
            i += 2
            continue
        body = parts[i + 1].strip()
        idx = num - 1
        if 0 <= idx < len(original_texts) and body:
            cache[original_texts[idx]] = body
        i += 2

    return cache


def _clean_attrs_str(html: str) -> str:
    """Remove style and class attributes from HTML string."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(True):
        if tag.has_attr("style"):
            del tag["style"]
        if tag.has_attr("class"):
            del tag["class"]
    return str(soup)


# ---------------------------------------------------------------------------
# HTML wrapping
# ---------------------------------------------------------------------------

def _wrap_page_html(html_content: str) -> str:
    """Wrap a page fragment in a full HTML document with styling."""
    if re.search(r"<html", html_content, re.IGNORECASE):
        if "</head>" in html_content:
            return html_content.replace("</head>", f"{_STYLE_INJECT}</head>")
        return html_content
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"{_STYLE_INJECT}</head><body>{html_content}</body></html>"
    )


# ---------------------------------------------------------------------------
# Concurrent page-by-page translation
# ---------------------------------------------------------------------------

def _translate_page_async(
    page_num: int,
    page_html: str,
    client: ZaiLLMClient,
    src: str,
    tgt: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Translate a single page, bounded by semaphore for concurrency control."""
    async def _do():
        async with semaphore:
            loop = asyncio.get_event_loop()
            translated_raw = await loop.run_in_executor(
                None, _translate_page, page_html, client, src, tgt,
            )
            translated_html = _wrap_page_html(translated_raw)
            original_html = _wrap_page_html(page_html)
            return {
                "page": page_num,
                "original_html": original_html,
                "translated_html": translated_html,
            }

    return _do()


async def _translate_pages_concurrent(
    pages: list[tuple[int, str]],
    client: ZaiLLMClient,
    src: str,
    tgt: str,
    output_dir: Path,
    on_page_done: Optional[Callable[[int, int, str, str], None]],
) -> list[dict]:
    """Translate pages concurrently with semaphore-limited parallelism."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    total_pages = len(pages)

    async def _translate_and_save(page_num: int, page_html: str) -> dict:
        result = await _translate_page_async(page_num, page_html, client, src, tgt, semaphore)

        (output_dir / f"page_{page_num}.html").write_text(
            result["translated_html"], encoding="utf-8",
        )

        if on_page_done:
            on_page_done(page_num, total_pages, result["original_html"], result["translated_html"])

        if _INTER_PAGE_DELAY > 0 and len(pages) > 1:
            await asyncio.sleep(_INTER_PAGE_DELAY)

        return result

    tasks = [_translate_and_save(pn, ph) for pn, ph in pages]
    results = await asyncio.gather(*tasks)

    # Sort by page number to maintain order
    results.sort(key=lambda r: r["page"])
    return results


def translate_html_by_pages(
    html_path: str | Path,
    output_dir: str | Path,
    source_lang: str = "ko",
    target_lang: str = "en",
    on_page_done: Optional[Callable[[int, int, str, str], None]] = None,
) -> list[dict]:
    """Translate an HTML document page by page with concurrent API calls.

    Uses asyncio + semaphore to translate up to 3 pages simultaneously,
    reducing total translation time by ~3x compared to sequential processing.

    Args:
        html_path: Path to the source HTML file.
        output_dir: Directory where translated page files are written.
        source_lang: Source language code (``"ko"`` or ``"en"``).
        target_lang: Target language code.
        on_page_done: ``callback(page_num, total_pages, original_html, translated_html)``

    Returns:
        List of dicts ``{"page", "original_html", "translated_html"}``.
    """
    lang_pair = {"ko": "Korean", "en": "English"}
    src = lang_pair.get(source_lang, source_lang)
    tgt = lang_pair.get(target_lang, target_lang)

    client = ZaiLLMClient(timeout=_TRANSLATION_TIMEOUT)

    html_content = Path(html_path).read_text(encoding="utf-8")
    pages = split_html_by_pages(html_content)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Starting translation: %d pages, model=%s, batch_size=%d, delay=%ds",
        len(pages), _settings.zai_llm_model, _BATCH_SIZE, _INTER_PAGE_DELAY,
    )

    # Check if already inside an event loop (e.g., FastAPI's)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in async context — run in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            results = pool.submit(
                asyncio.run,
                _translate_pages_concurrent(pages, client, src, tgt, out, on_page_done),
            ).result()
    else:
        results = asyncio.run(
            _translate_pages_concurrent(pages, client, src, tgt, out, on_page_done),
        )

    logger.info("Translation complete: %d pages", len(results))
    return results


# ---------------------------------------------------------------------------
# Legacy whole-document translation
# ---------------------------------------------------------------------------

def translate_html(
    html_path: str | Path,
    output_path: str | Path,
    source_lang: str = "ko",
    target_lang: str = "en",
    on_progress: Optional[Callable] = None,
) -> str:
    """Translate an entire HTML document in one pass (legacy)."""
    lang_pair = {"ko": "Korean", "en": "English"}
    src = lang_pair.get(source_lang, source_lang)
    tgt = lang_pair.get(target_lang, target_lang)

    client = ZaiLLMClient(timeout=_TRANSLATION_TIMEOUT)

    html_content = Path(html_path).read_text(encoding="utf-8")
    translated = _translate_page(html_content, client, src, tgt)
    translated = _wrap_page_html(translated)

    Path(output_path).write_text(translated, encoding="utf-8")

    if on_progress:
        on_progress(1, 1)

    return str(output_path)


# ---------------------------------------------------------------------------
# Plain text translation (chunk-based)
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 3000  # characters per chunk (~1-2 pages of text)

def _build_text_translate_prompt(src: str, tgt: str) -> str:
    return (
        f"You are a professional financial document translator. "
        f"Translate the following {src} text to {tgt}.\n"
        "Rules:\n"
        f"- Translate every word from {src} to {tgt}. Do not leave any untranslated text.\n"
        "- Do NOT translate numbers, percentages, dates, or currency symbols.\n"
        "- For company names, translate to their official name in the target language.\n"
        "- Preserve paragraph breaks and line structure.\n"
        "- No explanation or extra text — output ONLY the translation."
    )


def translate_text_chunks(
    text: str,
    source_lang: str = "ko",
    target_lang: str = "en",
    on_chunk_done: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """Translate plain text in chunks, returning the full translated text.

    Args:
        text: Source text to translate.
        source_lang: Source language code.
        target_lang: Target language code.
        on_chunk_done: ``callback(chunk_index, total_chunks, translated_text)``

    Returns:
        Full translated text.
    """
    # Split into chunks at paragraph boundaries
    paragraphs = text.split("\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > _CHUNK_SIZE and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_len = 0
        current_chunk.append(para)
        current_len += len(para) + 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    if not chunks:
        return ""

    lang_pair = {"ko": "Korean", "en": "English"}
    src = lang_pair.get(source_lang, source_lang)
    tgt = lang_pair.get(target_lang, target_lang)

    client = ZaiLLMClient(timeout=_TRANSLATION_TIMEOUT)

    translated_parts: list[str] = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            translated_parts.append("")
            continue

        for attempt in range(3):
            try:
                response = client._llm.invoke([
                    {"role": "system", "content": _build_text_translate_prompt(src, tgt)},
                    {"role": "user", "content": chunk},
                ])
                translated = response.content.strip()
                translated_parts.append(translated)
                break
            except Exception as exc:
                is_rate_limit = "429" in str(exc) or "rate" in str(exc).lower()
                base = 15 if is_rate_limit else 5
                wait = min(base * (2 ** attempt) + random.uniform(0, 5), 120)
                logger.warning(
                    "Text translation error chunk %d/%d (attempt %d/3): %s — waiting %.0fs",
                    i + 1, total, attempt + 1, exc, wait,
                )
                time.sleep(wait)
        else:
            logger.error("All attempts failed for chunk %d/%d", i + 1, total)
            translated_parts.append(chunk)  # keep original on failure

        if on_chunk_done:
            on_chunk_done(i + 1, total, translated_parts[-1])

    return "\n\n".join(translated_parts)
