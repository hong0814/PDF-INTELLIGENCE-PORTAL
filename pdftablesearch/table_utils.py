"""PDF 표 처리 유틸리티 — PyMuPDF 기반 표 감지, 매칭, 병합."""

from __future__ import annotations

import re


_HEADER_KEYWORDS = frozenset([
    "구분", "구 분", "계정", "주요계정", "연도", "종류", "항목", "구분",
    "분류", "항목", "세목", "유형", "영업년도",
])


def _table_col_count(html: str) -> int:
    m = re.search(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    return len(re.findall(r"<t[dh]", m.group(1))) if m else 0


def _table_first_row(html: str) -> list[str]:
    m = re.search(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    if not m:
        return []
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(1), re.DOTALL)
    return [re.sub(r"<[^>]+>", "", c).strip() for c in cells]


def _row_has_numbers(row: list[str]) -> bool:
    combined = " ".join(row)
    return bool(re.search(r"[\d,]+\.?\d*", combined))


def _row_has_header_keywords(row: list[str]) -> bool:
    combined = " ".join(row)
    return any(kw in combined for kw in _HEADER_KEYWORDS)


def _get_page_last_line(doc, pn: int) -> str:
    page = doc[pn - 1]
    text = page.get_text("text").strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return lines[-1] if lines else ""


def _extract_sub_title(text_above: str, max_lines: int = 3) -> str:
    lines = [l.strip() for l in text_above.split("\n") if l.strip()]
    if not lines:
        return ""
    taken = lines[-max_lines:]
    return "\n".join(taken)


def _enrich_tables_with_pymupdf(pdf_path: str, tables: list[dict]) -> None:
    try:
        import fitz
    except ImportError:
        return

    if not pdf_path or not tables:
        return

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return

    MAX_FITZ_TABLES = 200

    by_page: dict[int, list[dict]] = {}
    for t in tables:
        pn = t.get("page_number", 0)
        by_page.setdefault(pn, []).append(t)

    used_fitz_global: set[tuple[int, int]] = set()

    for pn, page_tables in by_page.items():
        if pn < 1 or pn > len(doc):
            continue

        page = doc[pn - 1]
        page_h = page.rect.height
        page_w = page.rect.width
        fitz_tables = page.find_tables().tables

        fitz_data: list[tuple] = []
        for fi, ft in enumerate(fitz_tables):
            data = ft.extract()
            ft_text = _normalize_text(" ".join(" ".join(str(c or "") for c in row) for row in data))
            fitz_data.append((fi, ft, ft_text))

        matched_fitz: set[int] = set()

        for t in page_tables:
            html_text = _normalize_text(_table_text_content(t.get("table_html", "")))
            if not html_text:
                continue

            best_score = 0.0
            best_fi = -1

            for fi, ft, ft_text in fitz_data:
                score = _table_match_score(html_text, ft_text)
                if score > best_score:
                    best_score = score
                    best_fi = fi

            if best_fi >= 0 and best_score > 0.15:
                matched_fitz.add(best_fi)
                ft = fitz_data[best_fi][1]
                fbbox = list(ft.bbox)
                pdf_bbox = [fbbox[0], page_h - fbbox[3], fbbox[2], page_h - fbbox[1]]

                t["bounding_box"] = [round(v, 2) for v in pdf_bbox]

                y_top_pymupdf = fbbox[1]
                clip = fitz.Rect(0, max(0, y_top_pymupdf - 50), page_w, y_top_pymupdf)
                text_above = page.get_text("text", clip=clip).strip()
                if text_above and len(text_above) <= 150:
                    sub = _extract_sub_title(text_above)
                    if sub and len(sub) <= 120:
                        if not t.get("table_title"):
                            t["table_title"] = sub
                        t["sub_title"] = sub
                elif not text_above and pn > 1:
                    prev_line = _get_page_last_line(doc, pn - 1)
                    if prev_line and len(prev_line) <= 80:
                        if not t.get("table_title"):
                            t["table_title"] = prev_line
                        t["sub_title"] = prev_line


        for fi, ft, ft_text in fitz_data:
            if fi in matched_fitz:
                continue
            fbbox = list(ft.bbox)
            fbbox_area = (fbbox[2] - fbbox[0]) * (fbbox[3] - fbbox[1])
            if fbbox_area < 5000:
                continue

            is_inner = False
            for fi2, ft2, _ in fitz_data:
                if fi2 == fi:
                    continue
                obbox = list(ft2.bbox)
                if (obbox[0] <= fbbox[0] and obbox[1] <= fbbox[1]
                        and obbox[2] >= fbbox[2] and obbox[3] >= fbbox[3]):
                    is_inner = True
                    break
            if is_inner:
                continue

            pdf_bbox = [fbbox[0], page_h - fbbox[3], fbbox[2], page_h - fbbox[1]]
            data = ft.extract()
            if not data:
                continue

            from bs4 import BeautifulSoup
            html_parts = ["<table>"]
            for ri, row in enumerate(data):
                tag = "th" if ri == 0 else "td"
                html_parts.append("<tr>" + "".join(f"<{tag}>{_escape_html(str(c or ''))}</{tag}>" for c in row) + "</tr>")
            html_parts.append("</table>")
            table_html = "".join(html_parts)

            table_title = ""
            sub_title = ""
            y_top_pymupdf = fbbox[1]
            clip = fitz.Rect(0, max(0, y_top_pymupdf - 50), page_w, y_top_pymupdf)
            text_above = page.get_text("text", clip=clip).strip()
            if text_above and len(text_above) <= 150:
                sub = _extract_sub_title(text_above)
                if sub and len(sub) <= 120:
                    table_title = sub
                    sub_title = sub
            elif not text_above and pn > 1:
                prev_line = _get_page_last_line(doc, pn - 1)
                if prev_line and len(prev_line) <= 80:
                    table_title = prev_line
                    sub_title = prev_line

            new_id = f"table_{pn}_fitz{fi}"
            new_table = {
                "table_id": new_id,
                "page_number": pn,
                "bounding_box": [round(v, 2) for v in pdf_bbox],
                "table_html": table_html,
                "table_title": table_title or None,
                "sub_title": sub_title or None,
                "document_name": tables[0].get("document_name", "") if tables else "",
            }
            tables.append(new_table)

        if len(tables) > MAX_FITZ_TABLES:
            break

    doc.close()


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _normalize_text(text: str) -> str:
    import re
    text = text.lower()
    text = re.sub(r'\s+', '', text)
    return text


def _table_text_content(html: str) -> str:
    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    except Exception:
        return ""


def _table_match_score(html_norm: str, fitz_norm: str) -> float:
    if not html_norm or not fitz_norm:
        return 0.0
    if fitz_norm in html_norm:
        return 0.9
    if html_norm in fitz_norm:
        return 0.9
    html_words = set(html_norm)
    fitz_words = set(fitz_norm)
    if not html_words or not fitz_words:
        return 0.0
    intersection = html_words & fitz_words
    union = html_words | fitz_words
    return len(intersection) / len(union)


def _extract_top_level_tables_with_nesting(html_path: str) -> list[dict]:
    from bs4 import BeautifulSoup
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    soup = BeautifulSoup(content, "html.parser")
    result = []
    for table_tag in soup.find_all("table"):
        parent = table_tag.parent
        is_nested = False
        p = parent
        while p:
            if p.name == "td":
                pp = p.parent
                while pp:
                    if pp.name == "table" and pp != table_tag:
                        is_nested = True
                        break
                    pp = pp.parent
                if is_nested:
                    break
            p = p.parent
        if is_nested:
            continue

        has_inner = bool(table_tag.find("table"))
        text = _normalize_text(table_tag.get_text(separator=" ", strip=True))
        result.append({
            "html": str(table_tag),
            "text": text,
            "has_nested_table": has_inner,
        })
    return result


def _build_tables_from_pymupdf(
    pdf_path: str,
    hybrid_tables: list[dict],
    standard_html_path: str | None,
) -> list[dict]:
    try:
        import fitz
    except ImportError:
        return hybrid_tables

    if not pdf_path:
        return hybrid_tables

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return hybrid_tables

    doc_name = hybrid_tables[0].get("document_name", "") if hybrid_tables else ""

    standard_tables: list[dict] = []
    if standard_html_path:
        standard_tables = _extract_top_level_tables_with_nesting(standard_html_path)

    hybrid_by_page: dict[int, list[dict]] = {}
    for t in hybrid_tables:
        pn = t.get("page_number", 0)
        hybrid_by_page.setdefault(pn, []).append(t)

    all_fitz: list[dict] = []
    for page_idx in range(len(doc)):
        pn = page_idx + 1
        page = doc[page_idx]
        page_h = page.rect.height
        page_w = page.rect.width
        fitz_tables = page.find_tables().tables

        fitz_data = []
        for fi, ft in enumerate(fitz_tables):
            fbbox = list(ft.bbox)
            area = (fbbox[2] - fbbox[0]) * (fbbox[3] - fbbox[1])
            if area < 5000:
                continue
            data = ft.extract()
            ft_text = _normalize_text(" ".join(" ".join(str(c or "") for c in row) for row in data))
            pdf_bbox = [fbbox[0], page_h - fbbox[3], fbbox[2], page_h - fbbox[1]]
            fitz_data.append({
                "fi": fi, "ft": ft, "bbox": fbbox, "pdf_bbox": pdf_bbox,
                "area": area, "text": ft_text, "data": data, "page": pn,
            })

        inner_indices = set()
        for i, fd in enumerate(fitz_data):
            for j, fd2 in enumerate(fitz_data):
                if i == j:
                    continue
                b1, b2 = fd["bbox"], fd2["bbox"]
                if (b2[0] <= b1[0] and b2[1] <= b1[1] and b2[2] >= b1[2] and b2[3] >= b1[3]):
                    inner_indices.add(i)

        for i, fd in enumerate(fitz_data):
            fd["is_inner"] = i in inner_indices
            all_fitz.append(fd)

    outer_fitz = [f for f in all_fitz if not f["is_inner"]]
    inner_fitz = [f for f in all_fitz if f["is_inner"]]

    for o in outer_fitz:
        o["inner_table_indices"] = []
    for idx, inn in enumerate(inner_fitz):
        for oi, o in enumerate(outer_fitz):
            ob = o["bbox"]
            ib = inn["bbox"]
            if (ob[0] <= ib[0] and ob[1] <= ib[1] and ob[2] >= ib[2] and ob[3] >= ib[3]
                    and o["page"] == inn["page"]):
                o["inner_table_indices"].append(idx)
                break

    results: list[dict] = []
    matched_hybrid_ids: set[str] = set()
    matched_standard: set[int] = set()

    for oi, o in enumerate(outer_fitz):
        has_inner = len(o["inner_table_indices"]) > 0
        table_html = ""
        source = "none"
        hybrid_bbox: list = []
        hybrid_title = ""

        if has_inner and standard_tables:
            best_score = 0.0
            best_si = -1
            for si, st in enumerate(standard_tables):
                if not st["has_nested_table"]:
                    continue
                if si in matched_standard:
                    continue
                score = _table_match_score(o["text"], st["text"])
                if score > best_score:
                    best_score = score
                    best_si = si
            if best_si >= 0 and best_score > 0.10:
                table_html = standard_tables[best_si]["html"]
                matched_standard.add(best_si)
                source = "standard"

        if not table_html:
            best_score = 0.0
            best_ht = None
            page_hybrid = hybrid_by_page.get(o["page"], [])
            for ht in page_hybrid:
                if ht.get("table_id", "") in matched_hybrid_ids:
                    continue
                ht_bbox = ht.get("bounding_box", [])
                if not ht_bbox or ht_bbox == [0, 0, 0, 0]:
                    continue
                html_text = _normalize_text(_table_text_content(ht.get("table_html", "")))
                text_score = _table_match_score(html_text, o["text"])
                score = text_score
                ya1, ya2 = o["pdf_bbox"][1], o["pdf_bbox"][3]
                yb1, yb2 = ht_bbox[1], ht_bbox[3]
                overlap_start = max(ya1, yb1)
                overlap_end = min(ya2, yb2)
                if overlap_start < overlap_end:
                    y_overlap = (overlap_end - overlap_start) / max(min(ya2 - ya1, yb2 - yb1), 1)
                    score = text_score * (0.5 + 0.5 * y_overlap)
                else:
                    score = text_score * 0.1
                if score > best_score:
                    best_score = score
                    best_ht = ht
            if best_ht and best_score > 0.10:
                table_html = best_ht.get("table_html", "")
                matched_hybrid_ids.add(best_ht.get("table_id", ""))
                hybrid_bbox = best_ht.get("bounding_box", [])
                hybrid_title = best_ht.get("table_title", "")
                source = "hybrid"

        if not table_html:
            data = o.get("data", [])
            if data:
                html_parts = ["<table>"]
                for ri, row in enumerate(data):
                    tag = "th" if ri == 0 else "td"
                    html_parts.append("<tr>" + "".join(f"<{tag}>{_escape_html(str(c or ''))}</{tag}>" for c in row) + "</tr>")
                html_parts.append("</table>")
                table_html = "".join(html_parts)
                source = "pymupdf"

        title = hybrid_title or ""
        sub_title = ""
        if not title:
            try:
                title_page = doc[o["page"] - 1]
                y_top = o["bbox"][1]
                clip = fitz.Rect(0, max(0, y_top - 50), title_page.rect.width, y_top)
                text_above = title_page.get_text("text", clip=clip).strip()
                if text_above and len(text_above) <= 150:
                    sub = _extract_sub_title(text_above)
                    if sub and len(sub) <= 120:
                        title = sub
            except Exception:
                pass

        try:
            title_page = doc[o["page"] - 1]
            y_top = o["bbox"][1]
            clip = fitz.Rect(0, max(0, y_top - 50), title_page.rect.width, y_top)
            text_above = title_page.get_text("text", clip=clip).strip()
            if text_above and len(text_above) <= 150:
                sub = _extract_sub_title(text_above)
                if sub and len(sub) <= 120:
                    sub_title = sub
            elif not text_above and o["page"] > 1:
                prev_line = _get_page_last_line(doc, o["page"] - 1)
                if prev_line and len(prev_line) <= 80:
                    sub_title = prev_line
        except Exception:
            pass

        inner_ids = []
        for inner_idx in o.get("inner_table_indices", []):
            inn = inner_fitz[inner_idx]
            inner_id = f"fitz_p{inn['page']}_{inn['fi']}_inner"
            inner_ids.append(inner_id)

            inn_bbox_pdf = inn["pdf_bbox"]
            # Find hybrid table whose bbox is contained within this inner table's PyMuPDF bbox
            page_hybrid = hybrid_by_page.get(o["page"], [])
            matched_hybrid = None
            for ht in page_hybrid:
                ht_bbox = ht.get("bounding_box", [])
                if not ht_bbox or ht_bbox == [0, 0, 0, 0]:
                    continue
                # ht bbox must be mostly inside the inner fitz bbox
                inn_y1, inn_y2 = inn_bbox_pdf[1], inn_bbox_pdf[3]
                ht_y1, ht_y2 = ht_bbox[1], ht_bbox[3]
                inn_x1, inn_x2 = inn_bbox_pdf[0], inn_bbox_pdf[2]
                ht_x1, ht_x2 = ht_bbox[0], ht_bbox[2]
                horz_overlap = max(0, min(inn_x2, ht_x2) - max(inn_x1, ht_x1))
                vert_overlap = max(0, min(inn_y2, ht_y2) - max(inn_y1, ht_y1))
                inn_area = (inn_x2 - inn_x1) * (inn_y2 - inn_y1)
                ht_area = (ht_x2 - ht_x1) * (ht_y2 - ht_y1)
                if inn_area > 0 and ht_area > 0:
                    overlap_ratio = (horz_overlap * vert_overlap) / min(inn_area, ht_area)
                    if overlap_ratio > 0.5:
                        matched_hybrid = ht
                        break

            if matched_hybrid:
                inn_html = matched_hybrid.get("table_html", "")
                inn_final_bbox = matched_hybrid.get("bounding_box", inn_bbox_pdf)
                inn_title = matched_hybrid.get("table_title", None)
                inn_source = "hybrid"
            else:
                inn_data = inn.get("data", [])
                inn_html = ""
                if inn_data:
                    inn_html_parts = ["<table>"]
                    for ri, row in enumerate(inn_data):
                        tag = "th" if ri == 0 else "td"
                        inn_html_parts.append("<tr>" + "".join(f"<{tag}>{_escape_html(str(c or ''))}</{tag}>" for c in row) + "</tr>")
                    inn_html_parts.append("</table>")
                    inn_html = "".join(inn_html_parts)
                inn_final_bbox = [round(v, 2) for v in inn_bbox_pdf]
                inn_title = None
                inn_source = "pymupdf"

            results.append({
                "table_id": inner_id,
                "hybrid_table_id": matched_hybrid.get("table_id", "") if matched_hybrid else "",
                "page_number": inn["page"],
                "bounding_box": inn_final_bbox,
                "table_html": inn_html,
                "table_title": inn_title,
                "document_name": doc_name,
                "has_inner_tables": False,
                "is_inner": True,
                "outer_table_id": f"fitz_p{o['page']}_{o['fi']}",
                "inner_table_ids": [],
                "_source": inn_source,
            })

        final_bbox = [round(v, 2) for v in o["pdf_bbox"]]

        results.append({
            "table_id": f"fitz_p{o['page']}_{o['fi']}",
            "hybrid_table_id": best_ht.get("table_id", "") if best_ht else "",
            "page_number": o["page"],
            "bounding_box": final_bbox,
            "table_html": table_html,
            "table_title": title or None,
            "sub_title": sub_title or None,
            "document_name": doc_name,
            "has_inner_tables": has_inner,
            "is_inner": False,
            "outer_table_id": None,
            "inner_table_ids": inner_ids,
            "_source": source,
        })

    doc.close()

    for pn, page_tables in hybrid_by_page.items():
        for ht in page_tables:
            ht_id = ht.get("table_id", "")
            if ht_id in matched_hybrid_ids:
                continue
            ht_copy = dict(ht)
            ht_copy["_source"] = "hybrid_fallback"
            ht_bbox = ht_copy.get("bounding_box", [])
            is_inner_hybrid = False
            if ht_bbox and len(ht_bbox) >= 4 and ht_bbox != [0, 0, 0, 0]:
                for r in results:
                    r_bbox = r.get("bounding_box", [])
                    if (r.get("page_number") == pn and r_bbox and len(r_bbox) >= 4
                            and r_bbox[0] <= ht_bbox[0] and r_bbox[1] <= ht_bbox[1]
                            and r_bbox[2] >= ht_bbox[2] and r_bbox[3] >= ht_bbox[3]):
                        is_inner_hybrid = True
                        break
            if is_inner_hybrid:
                continue
            results.append(ht_copy)

    return results


def _detect_multipage_tables(
    tables: list[dict],
) -> list[dict]:
    outer_tables = [t for t in tables if not t.get("is_inner") and t.get("_source") != "hybrid_fallback"]

    by_page: dict[int, list[dict]] = {}
    for t in outer_tables:
        pn = t.get("page_number", -1)
        by_page.setdefault(pn, []).append(t)

    sorted_pages = sorted(by_page.keys())

    raw_pairs: list[tuple[str, str, bool]] = []

    for pi in range(len(sorted_pages) - 1):
        pa, pb = sorted_pages[pi], sorted_pages[pi + 1]
        if pb != pa + 1:
            continue

        tables_a = by_page.get(pa, [])
        tables_b = by_page.get(pb, [])
        if not tables_a or not tables_b:
            continue

        last_on_a = None
        last_bbox = [0, 9999, 0, 0]
        for t in tables_a:
            bbox = t.get("bounding_box", [0, 0, 0, 0])
            if len(bbox) >= 4 and bbox != [0, 0, 0, 0] and bbox[1] < last_bbox[1]:
                last_on_a = t
                last_bbox = bbox

        first_on_b = None
        first_bbox = [0, 0, 0, 0]
        for t in tables_b:
            bbox = t.get("bounding_box", [0, 0, 0, 0])
            if len(bbox) >= 4 and bbox != [0, 0, 0, 0] and bbox[3] > first_bbox[3]:
                first_on_b = t
                first_bbox = bbox

        if not (last_on_a and first_on_b):
            continue

        bbox_a = last_on_a.get("bounding_box", [0, 0, 0, 0])
        bbox_b = first_on_b.get("bounding_box", [0, 0, 0, 0])
        if len(bbox_a) < 4 or len(bbox_b) < 4:
            continue

        a_near_bottom = bbox_a[1] < 200
        b_near_top = bbox_b[3] > 400

        if not (a_near_bottom and b_near_top):
            continue

        html_a = last_on_a.get("table_html", "") or last_on_a.get("html", "")
        html_b = first_on_b.get("table_html", "") or first_on_b.get("html", "")
        if not html_a or not html_b:
            continue

        cols_a = _table_col_count(html_a)
        cols_b = _table_col_count(html_b)
        same_cols = cols_a == cols_b and cols_a > 0
        table_at_very_top = bbox_b[3] > 700
        force_include = not same_cols and table_at_very_top

        if not same_cols and not force_include:
            continue

        raw_pairs.append((last_on_a["table_id"], first_on_b["table_id"], same_cols))
        tag = "paired" if same_cols else "paired (cols differ, table at very top)"

    # Transitive closure: A→B, B→C => chain [A, B, C]
    chains: list[list[str]] = []
    table_to_chain: dict[str, int] = {}

    for aid, bid, _ in raw_pairs:
        a_chain = table_to_chain.get(aid)
        b_chain = table_to_chain.get(bid)

        if a_chain is not None and b_chain is not None:
            if a_chain == b_chain:
                continue
            src, dst = (b_chain, a_chain) if len(chains[a_chain]) >= len(chains[b_chain]) else (a_chain, b_chain)
            for tid in chains[src]:
                table_to_chain[tid] = dst
            chains[dst].extend(chains[src])
            chains[src] = []
        elif a_chain is not None:
            chains[a_chain].append(bid)
            table_to_chain[bid] = a_chain
        elif b_chain is not None:
            chains[b_chain].insert(0, aid)
            table_to_chain[aid] = b_chain
        else:
            idx = len(chains)
            chains.append([aid, bid])
            table_to_chain[aid] = idx
            table_to_chain[bid] = idx

    chains = [c for c in chains if len(c) >= 2]

    by_id = {t["table_id"]: t for t in tables}

    results: list[dict] = []
    for ci, chain in enumerate(chains):
        gid = f"group_{ci}"

        pair_cols: list[tuple[bool, int, int]] = []
        for i in range(len(chain) - 1):
            ta = by_id.get(chain[i], {})
            tb = by_id.get(chain[i + 1], {})
            html_a = ta.get("table_html", "") or ta.get("html", "")
            html_b = tb.get("table_html", "") or tb.get("html", "")
            cols_a = _table_col_count(html_a) if html_a else 0
            cols_b = _table_col_count(html_b) if html_b else 0
            pair_cols.append((cols_a == cols_b and cols_a > 0, cols_a, cols_b))

        all_same = all(sc for sc, _, _ in pair_cols)

        tables_info = []
        for tid in chain:
            t = by_id.get(tid, {})
            tables_info.append({
                "table_id": tid,
                "page_number": t.get("page_number"),
                "bounding_box": t.get("bounding_box", []),
                "table_title": t.get("table_title"),
                "table_html": t.get("table_html", ""),
            })

        results.append({
            "group_id": gid,
            "tables": tables_info,
            "chain_length": len(chain),
            "same_cols": all_same,
            "pair_cols": pair_cols,
        })


    return results


def _apply_table_groups(
    session: dict, pdf_name: str, tier1: list[tuple[str, str, str]],
    tier2_confirmed: list[tuple[str, str, str]],
) -> None:
    tables = session["pdfs"][pdf_name].get("tables", [])
    by_id = {t["table_id"]: t for t in tables}

    for pairs in (tier1, tier2_confirmed):
        for aid, bid, gid in pairs:
            if aid in by_id:
                by_id[aid]["group_id"] = gid
            if bid in by_id:
                by_id[bid]["group_id"] = gid


def _merge_grouped_tables(tables: list[dict]) -> None:
    from bs4 import BeautifulSoup

    groups: dict[str, list[dict]] = {}
    for t in tables:
        gid = t.get("group_id")
        if gid:
            groups.setdefault(gid, []).append(t)

    for gid, group_tables in groups.items():
        if len(group_tables) < 2:
            continue

        group_table_ids = [t["table_id"] for t in group_tables]

        soup_a = BeautifulSoup(group_tables[0].get("table_html", ""), "html.parser")
        table_a = soup_a.find("table")
        if not table_a:
            continue

        first_header_texts: list[str] = []
        first_row_a = table_a.find("tr")
        if first_row_a:
            first_header_texts = [c.get_text(strip=True) for c in first_row_a.find_all(["td", "th"])]

        for tb in group_tables[1:]:
            soup_b = BeautifulSoup(tb.get("table_html", ""), "html.parser")
            table_b = soup_b.find("table")
            if not table_b:
                continue

            rows_b = table_b.find_all("tr")
            cols_a = len(first_row_a.find_all(["td", "th"])) if first_row_a else 0

            for row in rows_b:
                cells = row.find_all(["td", "th"])
                if cols_a > 0 and len(cells) == cols_a:
                    row_texts = [c.get_text(strip=True) for c in cells]
                    if row_texts == first_header_texts:
                        continue
                table_a.append(row)

        merged_html = str(soup_a)

        for t in group_tables:
            t["merged_table_html"] = merged_html
            t["group_table_ids"] = group_table_ids
