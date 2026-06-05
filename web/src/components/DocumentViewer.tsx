import { useState, useEffect, useCallback, useRef } from 'react';
import { useAppStore, type HighlightRegion } from '../store/useAppStore';
import { BASE } from '../api/client';
import { drawPIIMasks } from '../utils/piiDetection';

declare global { var pdfjsLib: any; }

interface TableOverlay {
  id: string;
  page: number;
  x: number; y: number; w: number; h: number;
  html: string;
  title: string | null;
  sub_title?: string | null;
  group_id?: string;
  group_table_ids?: string[];
  merged_html?: string;
  has_inner_tables?: boolean;
  is_inner?: boolean;
}

export type TableFilterMode = 'all' | 'outer' | 'inner' | 'inner-or-standalone';

const HIGHLIGHT_COLOR = 'rgba(255, 200, 0, 0.35)';
const HIGHLIGHT_BORDER_COLOR = 'rgba(255, 160, 0, 0.7)';

interface DocumentViewerProps {
  tableFilter?: TableFilterMode;
}

export default function DocumentViewer({ tableFilter = 'all' }: DocumentViewerProps) {
  const pdfs = useAppStore((s) => s.pdfs);
  const sessionId = useAppStore((s) => s.sessionId);
  const highlightRegion = useAppStore((s) => s.highlightRegion);
  const setHighlightRegion = useAppStore((s) => s.setHighlightRegion);
  const overlayVersion = useAppStore((s) => s.overlayVersion);
  const [selectedPdf, setSelectedPdf] = useState<string>(pdfs[0]?.name ?? '');
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState('');
  const [scale, setScale] = useState(1.5);
  const [loading, setLoading] = useState(false);
  const [overlays, setOverlays] = useState<TableOverlay[]>([]);
  const [activeOverlay, setActiveOverlay] = useState<TableOverlay | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pdfDocRef = useRef<any>(null);
  const highlightBboxRef = useRef<number[] | null>(null);

  const ensurePdfJs = useCallback(async () => {
    if (!window.pdfjsLib) {
      await new Promise<void>((resolve) => {
        const check = () => { if (window.pdfjsLib) resolve(); else setTimeout(check, 100); };
        check();
      });
    }
    const pdfjs = window.pdfjsLib;
    if (!pdfjs.GlobalWorkerOptions.workerSrc) {
      pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.0.379/build/pdf.worker.min.mjs';
    }
    return pdfjs;
  }, []);

  const renderCurrentPage = useCallback(async (pageNum: number, highlightBbox?: number[] | null) => {
    const pdfDoc = pdfDocRef.current;
    if (!pdfDoc || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const page = await pdfDoc.getPage(pageNum);
    const viewport = page.getViewport({ scale });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext('2d')!;
    await page.render({ canvasContext: ctx, viewport }).promise;

    try {
      const textContent = await page.getTextContent();
      const piiSpans: { text: string; x: number; y: number; w: number; h: number }[] = [];
      for (const item of textContent.items as any[]) {
        if (!item.str || !item.str.trim()) continue;
        const tx = window.pdfjsLib.Util.transform(viewport.transform, item.transform);
        const fontSize = Math.abs(tx[0]) || Math.abs(tx[3]) || 10;
        piiSpans.push({
          text: item.str,
          x: tx[4],
          y: tx[5] - fontSize,
          w: (item.width || item.str.length * fontSize * 0.6) * scale,
          h: fontSize * 1.2,
        });
      }
      drawPIIMasks(canvas, piiSpans);
    } catch (_) { /* PII mask failure must not break rendering */ }

    const bbox = highlightBbox ?? highlightBboxRef.current;
    if (bbox && bbox.length >= 4) {
      const [vx1, vy1] = viewport.convertToViewportPoint(bbox[0], bbox[3]);
      const [vx2, vy2] = viewport.convertToViewportPoint(bbox[2], bbox[1]);
      const hx = Math.min(vx1, vx2);
      const hy = Math.min(vy1, vy2);
      const hw = Math.abs(vx2 - vx1);
      const hh = Math.abs(vy2 - vy1);

      ctx.fillStyle = HIGHLIGHT_COLOR;
      ctx.fillRect(hx, hy, hw, hh);
      ctx.strokeStyle = HIGHLIGHT_BORDER_COLOR;
      ctx.lineWidth = 2;
      ctx.strokeRect(hx, hy, hw, hh);
    }
  }, [scale]);

  const reloadOverlays = useCallback(async (viewport: any) => {
    if (!selectedPdf) return;
    const res = await fetch(`${BASE}/documents/tables?name=${encodeURIComponent(selectedPdf)}&session_id=${encodeURIComponent(sessionId)}`);
    const data = await res.json();
    const newOverlays: TableOverlay[] = (data.tables || []).map((t: any) => {
      const bbox = t.bounding_box || [0, 0, 0, 0];
      const [vx1, vy1] = viewport.convertToViewportPoint(bbox[0], bbox[3]);
      const [vx2, vy2] = viewport.convertToViewportPoint(bbox[2], bbox[1]);
      return {
        id: t.table_id || '',
        page: t.page_number || 0,
        x: Math.min(vx1, vx2), y: Math.min(vy1, vy2),
        w: Math.abs(vx2 - vx1), h: Math.abs(vy2 - vy1),
        html: t.table_html || t.table_markdown || '',
        title: t.table_title || null,
        sub_title: t.sub_title || null,
        group_id: t.group_id || undefined,
        group_table_ids: t.group_table_ids || undefined,
        merged_html: t.merged_table_html || undefined,
        has_inner_tables: t.has_inner_tables || false,
        is_inner: t.is_inner || false,
      };
    });
    setOverlays(newOverlays);
  }, [selectedPdf, sessionId]);

  const goToPage = useCallback(async (pageNum: number) => {
    if (pageNum < 1 || pageNum > numPages || !numPages) return;
    setCurrentPage(pageNum);
    setPageInput('');
    setActiveOverlay(null);
    highlightBboxRef.current = null;
    setHighlightRegion(null);
    await renderCurrentPage(pageNum, null);
    const page = await pdfDocRef.current?.getPage(pageNum);
    if (page) {
      const viewport = page.getViewport({ scale });
      await reloadOverlays(viewport);
    }
  }, [numPages, renderCurrentPage, setHighlightRegion, scale, reloadOverlays]);

  const navigateToHighlightRef = useRef<HighlightRegion | null>(null);

  const loadPdf = useCallback(async (pdfName: string) => {
    setLoading(true);
    setSelectedPdf(pdfName);
    setActiveOverlay(null);
    setCurrentPage(1);
    setPageInput('');
    pdfDocRef.current = null;
    setNumPages(0);

    try {
      const pdfjs = await ensurePdfJs();
      const pdfUrl = `${BASE}/documents/pdf?name=${encodeURIComponent(pdfName)}&session_id=${encodeURIComponent(sessionId)}`;
      const pdfDoc = await pdfjs.getDocument(pdfUrl).promise;
      pdfDocRef.current = pdfDoc;
      setNumPages(pdfDoc.numPages);

      const pending = navigateToHighlightRef.current;
      const startPage = (pending && pending.documentName === pdfName) ? pending.pageNumber : 1;
      highlightBboxRef.current = (pending && pending.documentName === pdfName) ? pending.boundingBox : null;

      setCurrentPage(startPage);
      const page = await pdfDoc.getPage(startPage);
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: canvas.getContext('2d')!, viewport }).promise;

      try {
        const textContent = await page.getTextContent();
        const piiSpans: { text: string; x: number; y: number; w: number; h: number }[] = [];
        for (const item of textContent.items as any[]) {
          if (!item.str || !item.str.trim()) continue;
          const tx = window.pdfjsLib.Util.transform(viewport.transform, item.transform);
          const fontSize = Math.abs(tx[0]) || Math.abs(tx[3]) || 10;
          piiSpans.push({
            text: item.str,
            x: tx[4],
            y: tx[5] - fontSize,
            w: (item.width || item.str.length * fontSize * 0.6) * scale,
            h: fontSize * 1.2,
          });
        }
        drawPIIMasks(canvas, piiSpans);
      } catch (_) {}

      if (highlightBboxRef.current) {
        const ctx = canvas.getContext('2d')!;
        const bbox = highlightBboxRef.current;
        const [vx1, vy1] = viewport.convertToViewportPoint(bbox[0], bbox[3]);
        const [vx2, vy2] = viewport.convertToViewportPoint(bbox[2], bbox[1]);
        const hx = Math.min(vx1, vx2);
        const hy = Math.min(vy1, vy2);
        const hw = Math.abs(vx2 - vx1);
        const hh = Math.abs(vy2 - vy1);
        ctx.fillStyle = HIGHLIGHT_COLOR;
        ctx.fillRect(hx, hy, hw, hh);
        ctx.strokeStyle = HIGHLIGHT_BORDER_COLOR;
        ctx.lineWidth = 2;
        ctx.strokeRect(hx, hy, hw, hh);
      }

      navigateToHighlightRef.current = null;
      await reloadOverlays(viewport);
    } finally {
      setLoading(false);
    }
  }, [sessionId, scale, ensurePdfJs, reloadOverlays]);

  useEffect(() => {
    if (selectedPdf && !pdfs.find(p => p.name === selectedPdf)) {
      pdfDocRef.current = null;
      setSelectedPdf('');
      return;
    }
    if (!selectedPdf && pdfs.length > 0) {
      setSelectedPdf(pdfs[0].name);
      return;
    }
    if (selectedPdf) loadPdf(selectedPdf);
  }, [selectedPdf, pdfs, loadPdf]);

  useEffect(() => {
    if (pdfDocRef.current && currentPage > 0) {
      renderCurrentPage(currentPage).then(async () => {
        const page = await pdfDocRef.current.getPage(currentPage);
        const viewport = page.getViewport({ scale });
        await reloadOverlays(viewport);
      });
    }
  }, [scale]);

  useEffect(() => {
    if (pdfDocRef.current && currentPage > 0 && overlayVersion > 0) {
      pdfDocRef.current.getPage(currentPage).then((page: any) => {
        const viewport = page.getViewport({ scale });
        reloadOverlays(viewport);
      });
    }
  }, [overlayVersion]);

  useEffect(() => {
    if (!highlightRegion || pdfs.length === 0) return;

    if (selectedPdf !== highlightRegion.documentName) {
      navigateToHighlightRef.current = highlightRegion;
      setSelectedPdf(highlightRegion.documentName);
      return;
    }

    if (!pdfDocRef.current) return;

    highlightBboxRef.current = highlightRegion.boundingBox;
    renderCurrentPage(highlightRegion.pageNumber, highlightRegion.boundingBox).then(() => {
      setCurrentPage(highlightRegion.pageNumber);
    });
  }, [highlightRegion]);

  const handlePageInputSubmit = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      const num = parseInt(pageInput, 10);
      if (num > 0 && num <= numPages) goToPage(num);
      else setPageInput('');
    }
  }, [pageInput, numPages, goToPage]);

  const currentPageTables = overlays.filter(o => o.page === currentPage).filter(o => {
    if (tableFilter === 'outer') return !o.is_inner;
    if (tableFilter === 'inner') return o.is_inner;
    if (tableFilter === 'inner-or-standalone') return o.is_inner || !o.has_inner_tables;
    return true;
  });

  if (pdfs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-full px-6 fade-in">
        <div className="w-16 h-16 bg-surface-elevated border border-border rounded-2xl flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-text-primary mb-1">문서 보기</h2>
        <p className="text-sm text-text-muted">PDF를 업로드하면 문서를 확인할 수 있습니다.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <div className="w-48 flex flex-col shrink-0 border-r border-border bg-surface-elevated overflow-y-auto">
        <div className="p-3 border-b border-border-light">
          <p className="text-xs font-semibold text-text-secondary mb-2">문서 목록</p>
          <div className="space-y-1">
            {pdfs.map((pdf) => (
              <button
                key={pdf.name}
                onClick={() => setSelectedPdf(pdf.name)}
                className={`w-full text-left p-2 rounded-lg text-xs transition-colors ${
                  selectedPdf === pdf.name
                    ? 'bg-primary/10 border border-primary/20 text-primary'
                    : 'hover:bg-surface text-text-secondary border border-transparent'
                }`}
              >
                <span className="font-medium truncate block">{pdf.name}</span>
                <span className="text-[10px] text-text-muted">표 {pdf.table_count}개</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden bg-white rounded-br-lg">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-light bg-surface-elevated">
          <div className="flex items-center gap-2">
            <button onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1} className="p-1 rounded hover:bg-surface disabled:opacity-30">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <input
              type="text"
              value={pageInput || currentPage}
              onChange={(e) => { const v = e.target.value; if (/^\d*$/.test(v)) setPageInput(v); }}
              onFocus={() => setPageInput(String(currentPage))}
              onBlur={() => setPageInput('')}
              onKeyDown={handlePageInputSubmit}
              className="w-10 text-center text-sm text-text-secondary border border-border rounded bg-surface-elevated outline-none focus:border-primary"
            />
            <span className="text-sm text-text-muted">/ {numPages}</span>
            <button onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= numPages} className="p-1 rounded hover:bg-surface disabled:opacity-30">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          <div className="flex items-center gap-2">
            <a
              href={`${BASE}/documents/text?name=${encodeURIComponent(selectedPdf)}&session_id=${encodeURIComponent(sessionId)}`}
              download
              className="px-3 py-1.5 text-sm border border-border rounded-lg hover:bg-surface transition-colors text-text-secondary flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              TXT 다운로드
            </a>
            <a
              href={`${BASE}/documents/markdown?name=${encodeURIComponent(selectedPdf)}&session_id=${encodeURIComponent(sessionId)}`}
              download
              className="px-3 py-1.5 text-sm border border-border rounded-lg hover:bg-surface transition-colors text-text-secondary flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              MD 다운로드
            </a>
            <button onClick={() => setScale(s => Math.max(0.5, s - 0.25))} className="p-1 rounded hover:bg-surface text-text-secondary">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
              </svg>
            </button>
            <span className="text-xs text-text-muted w-10 text-center">{Math.round(scale * 100)}%</span>
            <button onClick={() => setScale(s => Math.min(3, s + 0.25))} className="p-1 rounded hover:bg-surface text-text-secondary">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
              </svg>
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-auto relative bg-gray-100">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center z-10">
              <div className="flex items-center gap-2 text-text-muted bg-white/80 px-4 py-2 rounded-lg">
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="text-sm">문서를 불러오는 중...</span>
              </div>
            </div>
          )}

          <div className="relative mx-auto" style={{ width: 'fit-content' }}>
            <canvas ref={canvasRef} className="shadow-lg" />
            {currentPageTables.map((overlay) => (
              <div
                key={overlay.id}
                onClick={() => setActiveOverlay(overlay)}
                className={`absolute cursor-pointer border-2 transition-colors rounded group ${overlay.group_id ? 'border-blue-400/60 bg-blue-400/10 hover:bg-blue-400/25 hover:border-blue-400/80' : 'border-accent/40 bg-accent/10 hover:bg-accent/25 hover:border-accent/70'}`}
                style={{
                  left: overlay.x, top: overlay.y,
                  width: overlay.w, height: overlay.h,
                }}
                title={overlay.sub_title ? `${overlay.title || ''} (${overlay.sub_title})` : (overlay.title || '클릭하여 CSV 다운로드')}
              >
                <span className="absolute -top-5 left-1 text-[9px] bg-accent text-white px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                  {overlay.title || `표`}
                  {overlay.sub_title && <span className="opacity-70 ml-1">· {overlay.sub_title}</span>}
                  {overlay.group_id && ' (연속표)'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {activeOverlay && (
          <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center fade-in" onClick={() => setActiveOverlay(null)}>
            <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-[90vw] max-h-[85vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-5 py-3 border-b shrink-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-text-primary">{activeOverlay.title || '표'}</span>
                  {activeOverlay.group_id && (
                    <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">연속표</span>
                  )}
                </div>
                <button onClick={() => setActiveOverlay(null)} className="text-text-muted hover:text-text-primary">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              {activeOverlay.group_table_ids && activeOverlay.group_table_ids.length > 1 && (
                <div className="px-5 py-2 border-b bg-blue-50/50 flex items-center gap-2 text-xs text-blue-700">
                  <span>연결 표:</span>
                  {activeOverlay.group_table_ids.map((tid) => {
                    const related = overlays.find(o => o.id === tid);
                    if (!related) return null;
                    return (
                      <button
                        key={tid}
                        onClick={async () => {
                          if (related.page !== currentPage) {
                            await goToPage(related.page);
                          }
                          setActiveOverlay(related);
                        }}
                        className={`px-2 py-1 rounded border transition-colors ${tid === activeOverlay.id ? 'bg-blue-600 text-white border-blue-600' : 'bg-white border-blue-200 hover:bg-blue-100'}`}
                      >
                        p.{related.page} {tid === activeOverlay.id ? '(현재)' : ''}
                      </button>
                    );
                  })}
                </div>
              )}
              <div className="flex-1 overflow-auto p-2">
                <iframe
                  srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:Pretendard,system-ui,sans-serif;padding:12px;margin:0}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border:1px solid #e2e8f0;padding:6px 8px;text-align:left}th{background-color:#dbeafe;font-weight:600}tr:nth-child(even)td{background-color:#f8fafc}</style></head><body>${activeOverlay.merged_html || activeOverlay.html}</body></html>`}
                  className="w-full border-0"
                  sandbox="allow-same-origin"
                  style={{ minHeight: '200px' }}
                  onLoad={(e) => {
                    const iframe = e.target as HTMLIFrameElement;
                    iframe.style.height = (iframe.contentDocument?.body?.scrollHeight ?? 200) + 'px';
                  }}
                />
              </div>
              <div className="px-5 py-3 border-t shrink-0">
                <button
                  onClick={() => {
                    const parser = new DOMParser();
                    const d = parser.parseFromString(activeOverlay.merged_html || activeOverlay.html, 'text/html');
                    const csvRows: string[] = [];
                    d.querySelectorAll('tr').forEach(tr => {
                      const cells: string[] = [];
                      tr.querySelectorAll('th, td').forEach(td => {
                        let text = td.textContent?.trim() ?? '';
                        if (text.includes(',') || text.includes('"')) text = '"' + text.replace(/"/g, '""') + '"';
                        cells.push(text);
                      });
                      if (cells.length) csvRows.push(cells.join(','));
                    });
                    const csv = '\uFEFF' + csvRows.join('\n');
                    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url; a.download = `${activeOverlay.id}.csv`;
                    document.body.appendChild(a); a.click(); document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                    setActiveOverlay(null);
                  }}
                  className="w-full px-3 py-2 text-sm bg-primary text-white rounded-lg hover:bg-primary-hover transition-colors"
                >
                  CSV 다운로드
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
