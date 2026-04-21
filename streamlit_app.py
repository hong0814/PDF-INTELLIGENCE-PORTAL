"""
Streamlit web demo for PDFTableSearch.

Allows users to upload PDFs, search for tables using natural language,
and view results with progress indicators.
"""

import sys
from pathlib import Path
from typing import List

import streamlit as st

# Add pdftablesearch to path
sys.path.insert(0, '/Users/a452779/Desktop/agent/corp/pdftablesearch')

from pdftablesearch import PDFTableSearch, TableSearchResult, smart_search

# -----------------------------------------------------------------------------
# Page configuration
# -----------------------------------------------------------------------------

st.set_page_config(
    page_title="PDF 테이블 검색",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 PDF 테이블 검색 시스템")
st.markdown("---")

# -----------------------------------------------------------------------------
# Session state initialization
# -----------------------------------------------------------------------------

if "pdfs" not in st.session_state:
    st.session_state.pdfs = {}  # {filename: {"status": "processed", "table_count": 0}}
if "searcher" not in st.session_state:
    st.session_state.searcher = None
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "last_upload_time" not in st.session_state:
    st.session_state.last_upload_time = None  # 마지막 업로드 처리 시간 (초)
if "last_search_time" not in st.session_state:
    st.session_state.last_search_time = None  # 마지막 검색 시간 (초)
if "last_search_prepare_time" not in st.session_state:
    st.session_state.last_search_prepare_time = None  # 마지막 검색 준비 시간 (초)
if "last_search_total_time" not in st.session_state:
    st.session_state.last_search_total_time = None  # 마지막 검색 총 시간 (초)
if "chroma_persist_dir" not in st.session_state:
    # 세션 단위로 고정된 ChromaDB 디렉토리 생성
    import tempfile
    st.session_state.chroma_persist_dir = tempfile.mkdtemp(prefix="pdftablesearch_chroma_session_")
if "searcher" not in st.session_state:
    # 세션 단위 searcher 초기화
    st.session_state.searcher = None

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def get_searcher():
    """Get or create session-specific PDFTableSearch instance."""
    if st.session_state.searcher is None:
        st.session_state.searcher = PDFTableSearch(
            chroma_persist_dir=st.session_state.chroma_persist_dir
        )
    return st.session_state.searcher


def clear_searcher_cache():
    """Clear the searcher cache."""
    if st.session_state.searcher:
        st.session_state.searcher.clear_cache()
    st.session_state.searcher = None


def process_uploaded_files(uploaded_files: List) -> dict:
    """Process uploaded PDF files and extract tables.

    Args:
        uploaded_files: List of uploaded file objects.

    Returns:
        Dictionary with processing results.
    """
    results = {}

    for uploaded_file in uploaded_files:
        filename = uploaded_file.name

        # Save uploaded file
        temp_path = Path(f"/tmp/pdftablesearch_{filename}")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        try:
            # Process PDF
            searcher = get_searcher()
            process_result = searcher.processor.load_documents(
                str(temp_path),
                use_hybrid=True,
            )

            # Get documents
            documents = searcher.processor.get_documents()

            results[filename] = {
                "status": "success",
                "table_count": len(documents),
                "tables": documents,
                "path": str(temp_path),
            }

        except Exception as exc:
            results[filename] = {
                "status": "error",
                "error": str(exc),
                "path": str(temp_path),
            }

    return results


def search_tables(query: str, pdf_name: str = None, max_results: int = 10) -> List[TableSearchResult]:
    """Search for tables using the loaded PDFs.

    Args:
        query: Search query.
        pdf_name: Optional specific PDF name to search in.
        max_results: Maximum number of results to return.

    Returns:
        List of search results.
    """
    import tempfile

    # Use dedicated temp directory for each search to avoid database locking
    temp_dir = tempfile.mkdtemp(prefix="pdftablesearch_search_")

    searcher = PDFTableSearch(chroma_persist_dir=temp_dir)

    if pdf_name and pdf_name in st.session_state.pdfs:
        pdf_path = st.session_state.pdfs[pdf_name].get("path")
        if pdf_path:
            try:
                return searcher.search(pdf_path, query, use_hybrid=True, k=max_results)
            except Exception as exc:
                # If first search fails, try with reset
                return searcher.search(pdf_path, query, use_hybrid=True, reset_vector_store=True, k=max_results)
    else:
        # Search in all loaded PDFs
        all_docs = []
        for pdf_data in st.session_state.pdfs.values():
            all_docs.extend(pdf_data.get("tables", []))

        if not all_docs:
            return []

        # Manual search for cached documents
        try:
            from pdftablesearch.vectorstore import TableVectorStore
            from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings

            embeddings = searcher.embeddings
            vector_store = TableVectorStore(embeddings=embeddings, persist_dir=temp_dir)
            vector_store.reset()
            vector_store.add_documents(all_docs)

            search_results = vector_store.similarity_search(query, k=max_results)

            return [
                TableSearchResult.from_langchain_document(doc, score)
                for doc, score in search_results[:max_results]
            ]
        except Exception as exc:
            st.error(f"검색 오류: {exc}")
            return []


def render_table_card(table: TableSearchResult, index: int):
    """Render a single table result as a card.

    Uses HTML rendering (``unsafe_allow_html=True``) when ``table_html`` is
    available, falling back to Markdown rendering for backward compatibility.

    Args:
        table: TableSearchResult object.
        index: Result index for display.
    """
    with st.container():
        # Show table title if available
        if table.table_title:
            st.markdown(f"### 🔍 결과 {index + 1}: {table.table_title}")
        else:
            st.markdown(f"### 🔍 결과 {index + 1}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("페이지", f"{table.page_number}쪽")
        with col2:
            # Convert distance to similarity (1 - distance = similarity)
            similarity = 1.0 - (table.relevance_score or 0.0)
            st.metric("관련도", f"{similarity:.3f}")
        with col3:
            st.metric("문서", table.document_name)

        with st.expander("📋 테이블 내용 보기", expanded=False):
            # Determine table content for display and download
            table_html = table.table_html
            table_md = table.table_markdown

            # Use HTML if available, otherwise fall back to markdown
            has_html = bool(table_html and table_html.strip())

            # Action buttons
            col1, col2, col3 = st.columns(3)

            with col1:
                # HTML download button
                if has_html:
                    # Wrap in basic styling for standalone viewing
                    styled_html = (
                        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>\n"
                        "<style>table{border-collapse:collapse;width:100%}"
                        "td,th{border:1px solid #ddd;padding:8px;text-align:left}"
                        "th{background-color:#f2f2f2}"
                        "</style></head><body>\n"
                        f"{table_html}\n</body></html>"
                    )
                    st.download_button(
                        label="📥 HTML",
                        data=styled_html,
                        file_name=f"table_{table.page_number}_{index + 1}.html",
                        mime="text/html",
                        use_container_width=True,
                    )
                else:
                    # Fallback: markdown download
                    st.download_button(
                        label="📥 Markdown",
                        data=table_md,
                        file_name=f"table_{table.page_number}_{index + 1}.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )

            with col2:
                # CSV download button (parse HTML or markdown table)
                import io
                import csv
                from bs4 import BeautifulSoup

                csv_lines = []
                if has_html:
                    soup = BeautifulSoup(table_html, "html.parser")
                    html_table = soup.find("table")
                    if html_table:
                        for tr in html_table.find_all("tr"):
                            cells = []
                            for td in tr.find_all(["td", "th"]):
                                cells.append(td.get_text(separator=" ", strip=True))
                            if cells:
                                csv_lines.append(cells)
                else:
                    for line in table_md.split('\n'):
                        if '|---' in line:
                            continue
                        if '|' in line:
                            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
                            csv_lines.append(cells)

                csv_output = io.StringIO()
                writer = csv.writer(csv_output)
                writer.writerows(csv_lines)
                csv_data = csv_output.getvalue()

                st.download_button(
                    label="📊 CSV",
                    data=csv_data,
                    file_name=f"table_{table.page_number}_{index + 1}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with col3:
                # Show as code block with copy button
                if st.button("📋 복사용 코드", key=f"code_btn_{index}_{table.table_id}", use_container_width=True):
                    st.session_state[f"show_code_{index}"] = not st.session_state.get(f"show_code_{index}", False)

            st.markdown("---")

            # Show code block if requested
            if st.session_state.get(f"show_code_{index}", False):
                code_content = table_html if has_html else table_md
                st.code(code_content, language="html" if has_html else "markdown")
                st.markdown("---")

            # Render the table
            if has_html:
                # Render HTML table with safe styling
                styled = (
                    "<div style='overflow-x:auto'>"
                    "<style>table.data-table{border-collapse:collapse;width:100%;font-size:13px}"
                    "table.data-table td,table.data-table th{border:1px solid #ddd;padding:6px 10px;text-align:left}"
                    "table.data-table th{background-color:#f2f2f2;font-weight:bold}"
                    "table.data-table tr:nth-child(even){background-color:#fafafa}"
                    "</style>"
                    f"<table class='data-table'>"
                )
                # Extract inner content from the <table> tag
                soup = BeautifulSoup(table_html, "html.parser")
                tbl = soup.find("table")
                if tbl:
                    inner = "".join(str(c) for c in tbl.children)
                    styled += inner
                else:
                    styled += table_html
                styled += "</table></div>"
                st.markdown(styled, unsafe_allow_html=True)
            else:
                st.markdown(table_md)

        st.markdown("---")


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 PDF 관리")

    # PDF upload
    uploaded_files = st.file_uploader(
        "PDF 파일 업로드",
        type=["pdf"],
        accept_multiple_files=True,
        help="검색할 PDF 파일을 선택하세요"
    )

    # Process uploaded files
    if uploaded_files:
        if st.button("📥 업로드 처리", type="primary"):
            import time
            with st.spinner("PDF 처리 중..."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                time_text = st.empty()

                start_time = time.time()

                status_text.text("📄 PDF 변환 및 테이블 추출 중...")
                progress_bar.progress(20)

                results = process_uploaded_files(uploaded_files)

                conversion_time = time.time() - start_time

                # Update session state
                for filename, result in results.items():
                    st.session_state.pdfs[filename] = result

                progress_bar.progress(100)

                total_time = time.time() - start_time
                st.session_state.last_upload_time = conversion_time  # 시간 저장

                time_text.text(f"⏱️ 변환: {conversion_time:.1f}초 | 총: {total_time:.1f}초")
                status_text.text(f"✅ 완료! {len(results)}개 PDF 처리됨 ({conversion_time:.1f}초)")

                st.success(f"{len(results)}개 PDF 업로드 완료! (소요 시간: {conversion_time:.1f}초)")
                st.rerun()

    # Display uploaded PDFs
    if st.session_state.pdfs:
        st.markdown("### 📋 업로드된 PDF")

        # 처리 시간 표시
        if st.session_state.last_upload_time:
            st.caption(f"⏱️ 마지막 업로드 처리 시간: {st.session_state.last_upload_time:.1f}초")

        total_tables = sum(
            pdf_data.get("table_count", 0)
            for pdf_data in st.session_state.pdfs.values()
        )

        st.info(f"📊 총 {total_tables}개 테이블")

        for filename, pdf_data in st.session_state.pdfs.items():
            if pdf_data.get("status") == "success":
                with st.container():
                    cols = st.columns([3, 1])
                    with cols[0]:
                        st.text(f"📄 {filename}")
                    with cols[1]:
                        if st.button("🗑️", key=f"del_{filename}"):
                            del st.session_state.pdfs[filename]
                            st.rerun()

                    st.caption(f"테이블: {pdf_data.get('table_count', 0)}개")
            else:
                st.error(f"❌ {filename}: {pdf_data.get('error', 'Unknown error')}")

        st.markdown("---")

        # Show all tables button (debugging)
        if st.button("🔍 전체 테이블 목록 보기", key="show_all_tables"):
            st.session_state.show_table_debug = not st.session_state.get("show_table_debug", False)

        if st.session_state.get("show_table_debug", False):
            st.markdown("### 📊 모든 테이블 목록")
            for filename, pdf_data in st.session_state.pdfs.items():
                if pdf_data.get("status") == "success":
                    st.markdown(f"**파일:** {filename}")
                    tables = pdf_data.get("tables", [])
                    for i, table_doc in enumerate(tables):
                        metadata = table_doc.metadata
                        page = metadata.get("page_number", "?")
                        title = metadata.get("table_title", "(제목 없음)")
                        content_preview = table_doc.page_content[:100].replace("\n", " ")

                        st.markdown(f"- **페이지 {page}**: {title}")
                        st.caption(f"내용 미리보기: {content_preview}...")
                    st.markdown("---")

        # Initialize button
        if st.button("🔄 전체 초기화", type="secondary"):
            if st.session_state.pdfs:
                st.session_state.pdfs.clear()
                clear_searcher_cache()
                st.success("초기화 완료! PDF를 다시 업로드해주세요.")
                st.rerun()

    # Usage instructions
    st.markdown("---")
    st.markdown("### 📖 사용법")
    st.markdown("""
    1. PDF 파일 업로드
    2. 검색어 입력
    3. 검색 결과 확인

    **팁**: 한 번 업로드 후 여러 번 검색 가능!
    """)

# -----------------------------------------------------------------------------
# Main content
# -----------------------------------------------------------------------------

if not st.session_state.pdfs:
    st.info("👈 왼쪽에서 PDF 파일을 업로드해주세요!")
else:
    # Search interface
    st.markdown("## 🔍 테이블 검색")

    # 마지막 검색 시간 표시 (준비 + 검색 + 총)
    if st.session_state.last_search_total_time:
        prepare = st.session_state.last_search_prepare_time or 0
        search = st.session_state.last_search_time or 0
        total = st.session_state.last_search_total_time
        st.caption(f"⏱️ 준비: {prepare:.1f}초 | 검색: {search:.1f}초 | 총: {total:.1f}초")

    # Query input
    query = st.text_input(
        "검색어를 입력하세요",
        placeholder="예: 사업성 평가 결과, 정리 재구조화, 연체율...",
        key="search_query"
    )

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        max_results = st.slider("최대 결과", 1, 20, 5)
    with col2:
        search_button = st.button("🔎 검색", type="primary", use_container_width=True)
    with col3:
        all_pdfs = st.checkbox("모든 PDF 검색", value=True)
    with col4:
        smart_search = st.checkbox("🧠 Smart Search", value=False, help="AI가 가장 적합한 테이블을 선택합니다")

    # Debug options
    with st.expander("🔧 디버그 옵션"):
        debug_mode = st.checkbox("디버그 모드", value=False, help="검색 후보 목록과 LLM 응답을 표시합니다")

    # Search
    if search_button and query:
        if not query.strip():
            st.warning("검색어를 입력해주세요!")
        else:
            import time
            with st.spinner(f"'{query}' 검색 중..."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                time_text = st.empty()

                search_start = time.time()

                # Step 1: Prepare
                status_text.text("🔍 검색 준비 중...")
                progress_bar.progress(10)
                prepare_time = time.time() - search_start
                time_text.text(f"준비: {prepare_time:.1f}초")

                # Step 2: Search
                status_text.text("🔍 테이블 검색 중...")
                progress_bar.progress(30)

                try:
                    # Perform search
                    if all_pdfs:
                        # Search in all PDFs
                        if smart_search:
                            # Smart Search: LLM으로 가장 적합한 1개 선택 + 벡터 검색 상위 2개 추가
                            from pdftablesearch import smart_search
                            import tempfile
                            pdf_name = list(st.session_state.pdfs.keys())[0]
                            pdf_path = st.session_state.pdfs[pdf_name].get("path")
                            if pdf_path:
                                status_text.text("🧠 AI 분석 중...")
                                progress_bar.progress(50)

                                # Smart Search를 위한 전용 임시 디렉토리 사용
                                smart_search_temp_dir = tempfile.mkdtemp(prefix="pdftablesearch_smart_search_")

                                # LLM이 1개 선택
                                ai_result = smart_search(
                                    query=query,
                                    pdf_path=pdf_path,
                                    top_k=20,
                                    use_hybrid=True,
                                    chroma_persist_dir=smart_search_temp_dir
                                )

                                # 벡터 검색으로 추가 결과 2개 가져오기 (AI 선택 결과 제외)
                                vector_results = search_tables(query, max_results=5)

                                # 디버그 모드: 벡터 검색 후보 표시
                                if debug_mode and vector_results:
                                    with st.expander("🔍 벡터 검색 상위 후보 (디버그)"):
                                        for i, vr in enumerate(vector_results[:5]):
                                            st.markdown(f"**{i+1}위** (페이지 {vr.page_number}): {vr.table_title or '(제목 없음)'}")
                                            st.caption(f"관련도: {1.0 - (vr.relevance_score or 0):.3f} | 테이블 ID: {vr.table_id}")
                                            preview = vr.table_html[:200] if vr.table_html else vr.table_markdown[:200]
                                            lang = "html" if vr.table_html else "markdown"
                                            st.code(preview + "...", language=lang)

                                # AI 선택 결과를 제외한 상위 2개 추가
                                additional_results = []
                                if vector_results:
                                    for vr in vector_results:
                                        # AI 선택 결과와 table_id가 다른 것만 추가
                                        if ai_result and vr.table_id != ai_result.table_id:
                                            additional_results.append(vr)
                                            if len(additional_results) >= 2:
                                                break

                                # 결과 합치기: AI 선택 1위 + 벡터 검색 2,3위
                                results = []
                                if ai_result:
                                    results.append(ai_result)
                                results.extend(additional_results[:2])

                                search_time = time.time() - search_start
                                time_text.text(f"검색: {search_time:.1f}초")
                            else:
                                results = []
                                search_time = time.time() - search_start
                                time_text.text(f"검색: {search_time:.1f}초")
                        else:
                            # Normal vector search
                            results = search_tables(query, max_results=max_results)
                            search_time = time.time() - search_start
                            time_text.text(f"검색: {search_time:.1f}초")
                    else:
                        # Search in first PDF only
                        pdf_name = list(st.session_state.pdfs.keys())[0]
                        results = search_tables(query, pdf_name, max_results=max_results)
                        search_time = time.time() - search_start
                        time_text.text(f"검색: {search_time:.1f}초")

                    progress_bar.progress(90)

                    # Display results
                    total_time = time.time() - search_start
                    search_only_time = total_time - prepare_time  # 실제 검색 시간

                    # 세션 상태에 시간 저장
                    st.session_state.last_search_prepare_time = prepare_time
                    st.session_state.last_search_time = search_only_time
                    st.session_state.last_search_total_time = total_time

                    time_text.text(f"총: {total_time:.1f}초")
                    status_text.text("✅ 검색 완료!")
                    progress_bar.progress(100)

                    if results:
                        if smart_search:
                            # Smart Search 결과
                            ai_count = 1  # AI가 선택한 1개
                            additional_count = len(results) - ai_count  # 추가 결과

                            st.success(f"🎉 AI가 선택한 가장 적합한 테이블 + {additional_count}개 추천! (준비 {prepare_time:.1f}초 | 검색 {search_only_time:.1f}초 | 총 {total_time:.1f}초)")
                            st.markdown("---")

                            # AI 선택 결과 표시 (첫 번째)
                            if results:
                                st.markdown("### 🏆 AI가 선택한 테이블")
                                render_table_card(results[0], 0)
                                st.info("💡 Smart Search: LLM이 '{query}' 검색어에 가장 적합한 테이블을 선택했습니다.")

                                # 추가 결과 표시
                                if additional_count > 0:
                                    st.markdown("---")
                                    st.markdown("### 📊 추가 추천 테이블")
                                    for i in range(1, min(ai_count + additional_count, len(results)) + 1):
                                        if i < len(results):
                                            render_table_card(results[i], i)
                        else:
                            st.success(f"🎉 {len(results)}개 테이블 찾음! (준비 {prepare_time:.1f}초 | 검색 {search_only_time:.1f}초 | 총 {total_time:.1f}초)")
                            st.markdown("---")

                            for i, table in enumerate(results):
                                render_table_card(table, i)
                    else:
                        st.warning("😕 관련 테이블을 찾지 못했어요.")
                        st.info("💡 다른 검색어를 시도해보세요!")

                except Exception as exc:
                    st.error(f"❌ 검색 오류: {exc}")
                    import traceback
                    st.error(traceback.format_exc())

                # Clear progress
                time.sleep(0.3)
                progress_bar.empty()
                status_text.empty()
                time_text.empty()

    # Quick search suggestions
    with st.expander("💡 검색어 추천"):
        suggestions = [
            "사업성 평가 결과",
            "정리 재구조화",
            "PF대출 연체율",
            "금융권 지원",
            "부동산 PF 현황"
        ]

        cols = st.columns(3)
        for i, suggestion in enumerate(suggestions):
            with cols[i % 3]:
                if st.button(suggestion, key=f"suggest_{i}"):
                    st.session_state.search_query = suggestion
                    st.rerun()

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    <small>Powered by PDFTableSearch | LangChain + ChromaDB + SentenceTransformers</small>
    </div>
    """,
    unsafe_allow_html=True
)
