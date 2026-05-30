import { useState, useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '../store/useAppStore';
import * as api from '../api/client';
import { BASE } from '../api/client';

declare global { var pdfjsLib: any; }

const HTML_STYLES = `
  html { font-size: 13px; }
  body {
    font-family: Pretendard, -apple-system, system-ui, sans-serif;
    margin: 0; padding: 16px; line-height: 1.7; color: #1e293b;
    max-width: 100%; word-break: break-word;
  }
  img { display: none !important; }
  table {
    width: 100%; border-collapse: collapse; margin: 12px 0;
    font-size: 12px; border-radius: 8px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  td, th { border: 1px solid #e2e8f0; padding: 7px 10px; text-align: left; }
  th { background-color: #dbeafe; font-weight: 600; color: #1e40af; }
  tr:nth-child(even) td { background-color: #f8fafc; }
  tr:hover td { background-color: #eff6ff; }
  p { margin: 6px 0; }
  h1 { font-size: 18px; font-weight: 700; margin: 20px 0 10px; color: #0f172a; border-bottom: 2px solid #dbeafe; padding-bottom: 6px; }
  h2 { font-size: 15px; font-weight: 600; margin: 16px 0 8px; color: #1e293b; }
  h3 { font-size: 14px; font-weight: 600; margin: 12px 0 6px; color: #334155; }
  h4 { font-size: 13px; font-weight: 600; margin: 10px 0 4px; color: #475569; }
  strong, b { color: #0f172a; }
  ul, ol { padding-left: 20px; margin: 6px 0; }
  li { margin: 3px 0; }
  hr { border: none; border-top: 1px solid #e2e8f0; margin: 16px 0; }
`;

function stripImages(html: string): string {
  return html.replace(/<img[^>]*>/gi, '').replace(/<svg[^>]*>[\s\S]*?<\/svg>/gi, '');
}

export default function TranslationView() {
  const sessionId = useAppStore((s) => s.sessionId);
  const pdfs = useAppStore((s) => s.pdfs);

  const [selectedPdf, setSelectedPdf] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [koHtml, setKoHtml] = useState('');
  const [enHtml, setEnHtml] = useState('');
  const isTranslating = useAppStore((s) => s.isTranslating);
  const setIsTranslating = useAppStore((s) => s.setIsTranslating);
  const translationProgress = useAppStore((s) => s.translationProgress);
  const setTranslationProgress = useAppStore((s) => s.setTranslationProgress);
  const translatedPages = useAppStore((s) => s.translatedPages);
  const setTranslatedPage = useAppStore((s) => s.setTranslatedPage);
  const [pdfLoading, setPdfLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pdfDocRef = useRef<any>(null);

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

  useEffect(() => {
    if (!selectedPdf && pdfs.length > 0) {
      setSelectedPdf(pdfs[0].name);
    }
  }, [pdfs, selectedPdf]);

  const loadPdf = useCallback(async (pdfName: string, page: number = 1) => {
    setPdfLoading(true);
    try {
      const pdfjs = await ensurePdfJs();
      const pdfUrl = `${BASE}/documents/pdf?name=${encodeURIComponent(pdfName)}&session_id=${encodeURIComponent(sessionId)}`;
      const pdfDoc = await pdfjs.getDocument(pdfUrl).promise;
      pdfDocRef.current = pdfDoc;
      setTotalPages(pdfDoc.numPages);
      setCurrentPage(page);

      const pdfPage = await pdfDoc.getPage(page);
      const viewport = pdfPage.getViewport({ scale: 1.5 });
      const canvas = canvasRef.current;
      if (canvas) {
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext('2d');
        if (ctx) {
          await pdfPage.render({ canvasContext: ctx, viewport }).promise;
        }
      }
    } catch (err) {
      console.error('PDF load error:', err);
    } finally {
      setPdfLoading(false);
    }
  }, [sessionId, ensurePdfJs]);

  const loadPageHtml = useCallback(async (pdfName: string, page: number) => {
    try {
      const html = await api.getPageHtml(pdfName, page, sessionId);
      setKoHtml(stripImages(html));
    } catch {
      setKoHtml('<p style="color:#94a3b8;text-align:center;padding:40px">페이지 HTML을 불러올 수 없습니다.</p>');
    }

    const cached = translatedPages[pdfName]?.[page];
    if (cached) {
      setEnHtml(cached);
    } else {
      try {
        const translated = await api.getTranslatedPage(pdfName, page, sessionId);
        setEnHtml(translated);
        setTranslatedPage(pdfName, page, translated);
      } catch {
        setEnHtml('<p style="color:#94a3b8;text-align:center;padding:40px">번역이 아직 완료되지 않았습니다.<br/>잠시만 기다려주세요.</p>');
      }
    }
  }, [sessionId, translatedPages, setTranslatedPage]);

  useEffect(() => {
    if (selectedPdf && sessionId) {
      setEnHtml('');
      setKoHtml('');
      loadPdf(selectedPdf);
    }
  }, [selectedPdf]);

  useEffect(() => {
    if (selectedPdf && currentPage && sessionId) {
      loadPageHtml(selectedPdf, currentPage);
    }
  }, [selectedPdf, currentPage, sessionId]);

  const handleTranslate = useCallback(async (targetLang: 'en' | 'ko') => {
    if (!selectedPdf || !sessionId) return;
    setIsTranslating(true);
    setTranslationProgress(targetLang === 'en' ? '영어 번역 준비 중...' : '한글 번역 준비 중...');
    abortRef.current = new AbortController();

    try {
      await api.startHtmlTranslation(
        selectedPdf,
        sessionId,
        targetLang === 'en' ? 'ko' : 'en',
        targetLang,
        (page, total, _orig, translated) => {
          setTranslatedPage(selectedPdf, page, translated);
          setTranslationProgress(`페이지 ${page}/${total} 번역 완료`);
          if (page === currentPage) {
            setEnHtml(translated);
          }
        },
        abortRef.current.signal,
      );
      const count = Object.keys(translatedPages[selectedPdf] || {}).length;
      setTranslationProgress(`번역 완료 (${count}페이지)`);
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setTranslationProgress('번역이 중단되었습니다.');
      } else {
        setTranslationProgress(`번역 오류: ${err.message}`);
      }
    } finally {
      setIsTranslating(false);
      abortRef.current = null;
    }
  }, [selectedPdf, sessionId, currentPage, translatedPages, setTranslatedPage, setTranslationProgress, setIsTranslating]);

  const handleAbortTranslation = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const goToPage = useCallback(async (page: number) => {
    if (page < 1 || page > totalPages) return;
    setCurrentPage(page);
    const doc = pdfDocRef.current;
    const canvas = canvasRef.current;
    if (!doc || !canvas) return;
    try {
      const pdfPage = await doc.getPage(page);
      const viewport = pdfPage.getViewport({ scale: 1.5 });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext('2d');
      if (ctx) await pdfPage.render({ canvasContext: ctx, viewport }).promise;
    } catch (err) {
      console.error('Page render error:', err);
    }
  }, [totalPages]);

  if (pdfs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-full px-6 py-16">
        <svg className="w-16 h-16 text-border mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m10.5 21 5.25-11.25L21 21m-9-3h7.5M3 5.621a48.474 48.474 0 0 1 6-.371m0 0c1.12 0 2.233.038 3.334.114M9 5.25V3m3.334 2.364C11.176 10.658 7.69 15.08 3 17.502m9.334-12.138c.896.061 1.785.147 2.666.257m-4.589 8.495a18.023 18.023 0 0 1-3.827-5.802" />
        </svg>
        <p className="text-text-muted text-sm">PDF를 먼저 업로드해주세요</p>
      </div>
    );
  }

  const makeIframeSrc = (html: string) =>
    `<!DOCTYPE html><html><head><meta charset="utf-8"><style>${HTML_STYLES}</style></head><body>${html}</body></html>`;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-surface-elevated flex-shrink-0">
        <div className="flex items-center gap-3">
          {pdfs.length > 1 && (
            <select
              value={selectedPdf}
              onChange={(e) => setSelectedPdf(e.target.value)}
              className="text-sm border border-border rounded-lg px-3 py-1.5 bg-surface text-text-primary focus:outline-none focus:border-primary"
            >
              {pdfs.map((p) => (
                <option key={p.name} value={p.name}>{p.name}</option>
              ))}
            </select>
          )}

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => goToPage(currentPage - 1)}
              disabled={currentPage <= 1}
              className="px-2.5 py-1 text-sm rounded border border-border hover:bg-surface-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              ‹
            </button>
            <span className="text-sm text-text-secondary tabular-nums min-w-[60px] text-center">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => goToPage(currentPage + 1)}
              disabled={currentPage >= totalPages}
              className="px-2.5 py-1 text-sm rounded border border-border hover:bg-surface-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              ›
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {translationProgress && (
            <span className="text-xs text-text-muted max-w-[300px] truncate">{translationProgress}</span>
          )}
          {isTranslating && (
            <button
              onClick={handleAbortTranslation}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-danger/10 text-danger border border-danger/30 hover:bg-danger/20 transition-colors flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
              중단
            </button>
          )}
          <button
            onClick={() => handleTranslate('ko')}
            disabled={isTranslating || !selectedPdf}
            className={`
              px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5
              ${isTranslating
                ? 'bg-primary/10 text-primary cursor-wait'
                : 'bg-surface-elevated text-text-primary border border-border hover:bg-surface'
              }
            `}
          >
            {isTranslating && <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />}
            한글로 번역
          </button>
          <button
            onClick={() => handleTranslate('en')}
            disabled={isTranslating || !selectedPdf}
            className={`
              px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5
              ${isTranslating
                ? 'bg-primary/10 text-primary cursor-wait'
                : 'bg-primary text-white hover:bg-primary/90'
              }
            `}
          >
            {isTranslating && <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />}
            영어로 번역
          </button>
        </div>
      </div>

      {/* 3-column content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Original PDF */}
        <div className="flex-1 border-r border-border overflow-auto bg-surface flex flex-col items-center">
          <div className="text-xs font-medium text-text-muted px-4 py-2 uppercase tracking-wide bg-surface-elevated w-full text-center border-b border-border-light">
            원본 PDF
          </div>
          <div className="p-4 flex justify-center">
            <div className="relative inline-block">
              {pdfLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-surface/80 z-10 min-h-[400px]">
                  <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                </div>
              )}
              <canvas ref={canvasRef} className="max-w-full shadow-lg rounded" />
            </div>
          </div>
        </div>

        {/* Middle: Original HTML */}
        <div className="flex-1 border-r border-border overflow-auto bg-white flex flex-col">
          <div className="text-xs font-medium text-text-muted px-4 py-2 uppercase tracking-wide bg-surface-elevated w-full text-center border-b border-border-light flex-shrink-0">
            원본
          </div>
          <div className="flex-1 overflow-auto">
            {koHtml ? (
              <iframe
                srcDoc={makeIframeSrc(koHtml)}
                className="w-full border-0"
                style={{ minHeight: '100%' }}
                sandbox="allow-same-origin"
                onLoad={(e) => {
                  const iframe = e.target as HTMLIFrameElement;
                  if (iframe.contentDocument?.body) {
                    iframe.style.height = Math.max(iframe.contentDocument.body.scrollHeight, 600) + 'px';
                  }
                }}
              />
            ) : (
              <div className="flex items-center justify-center h-64 text-text-muted text-sm">
                <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin mr-2" />
                로딩 중...
              </div>
            )}
          </div>
        </div>

        {/* Right: Translation */}
        <div className="flex-1 overflow-auto bg-white flex flex-col">
          <div className="text-xs font-medium text-text-muted px-4 py-2 uppercase tracking-wide bg-surface-elevated w-full text-center border-b border-border-light flex-shrink-0">
            번역본
          </div>
          <div className="flex-1 overflow-auto">
            {enHtml ? (
              <iframe
                srcDoc={makeIframeSrc(enHtml)}
                className="w-full border-0"
                style={{ minHeight: '100%' }}
                sandbox="allow-same-origin"
                onLoad={(e) => {
                  const iframe = e.target as HTMLIFrameElement;
                  if (iframe.contentDocument?.body) {
                    iframe.style.height = Math.max(iframe.contentDocument.body.scrollHeight, 600) + 'px';
                  }
                }}
              />
            ) : (
              <div className="flex items-center justify-center h-64 text-text-muted text-sm">
                <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin mr-2" />
                로딩 중...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
