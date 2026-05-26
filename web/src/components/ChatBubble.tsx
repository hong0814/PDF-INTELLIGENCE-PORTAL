import { useState, useEffect, useRef } from 'react';
import type { QAMessage } from '../types';
import { useAppStore } from '../store/useAppStore';
import { BASE } from '../api/client';

declare global { var pdfjsLib: any; }

interface Props {
  message: QAMessage;
}

type PopupSource = { pdf: string; page_number: number; paragraph_id?: string; text: string };

function ChunkPopup({ source, onClose }: { source: PopupSource; onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sessionId = useAppStore((s) => s.sessionId);
  const [activeTab, setActiveTab] = useState<'pdf' | 'text'>('pdf');

  useEffect(() => {
    let cancelled = false;
    const render = async () => {
      if (!window.pdfjsLib) {
        await new Promise<void>(r => {
          const c = () => { if (window.pdfjsLib) r(); else setTimeout(c, 100); };
          c();
        });
      }
      if (cancelled) return;
      const pdfjs = window.pdfjsLib;
      if (!pdfjs.GlobalWorkerOptions.workerSrc) {
        pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.0.379/build/pdf.worker.min.mjs';
      }
      const url = `${BASE}/documents/pdf?name=${encodeURIComponent(source.pdf)}&session_id=${encodeURIComponent(sessionId)}`;
      try {
        const pdf = await pdfjs.getDocument(url).promise;
        if (cancelled) return;
        const page = await pdf.getPage(source.page_number);
        const scale = 1.3;
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        if (!canvas) return;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext('2d')!;
        await page.render({ canvasContext: ctx, viewport }).promise;

        const textContent = await page.getTextContent();
        const items = textContent.items as Array<{ str: string; transform: number[]; width: number; height: number }>;

        type Span = { text: string; x: number; y: number; w: number; h: number };
        const spans: Span[] = [];
        for (const item of items) {
          if (!item.str.trim()) continue;
          const tx = pdfjs.Util.transform(viewport.transform, item.transform);
          const fontSize = Math.abs(tx[0]) || Math.abs(tx[3]) || 10;
          spans.push({
            text: item.str,
            x: tx[4],
            y: tx[5] - fontSize,
            w: item.width || (item.str.length * fontSize * 0.6),
            h: fontSize * 1.2,
          });
        }

        const normalize = (s: string) => s.replace(/[\s\.,;:!?·•\-()\[\]{}<>\/\\'"~,=%&#@+\u00A0]+/g, '');

        const charToSpan: number[] = [];
        let pageClean = '';
        for (let si = 0; si < spans.length; si++) {
          const clean = normalize(spans[si].text);
          for (let c = 0; c < clean.length; c++) {
            charToSpan.push(si);
          }
          pageClean += clean;
        }

        const sourceClean = normalize(source.text);

        const matchedSpanSet = new Set<number>();

        // Approach 1: full normalized match
        const fullIdx = pageClean.indexOf(sourceClean);
        if (fullIdx >= 0) {
          for (let i = fullIdx; i < fullIdx + sourceClean.length && i < charToSpan.length; i++) {
            matchedSpanSet.add(charToSpan[i]);
          }
        }

        // Approach 2: prefix match (first 20 normalized chars)
        if (matchedSpanSet.size === 0 && sourceClean.length > 20) {
          const prefixIdx = pageClean.indexOf(sourceClean.slice(0, 20));
          if (prefixIdx >= 0) {
            let matchLen = 0;
            for (let i = 0; i < sourceClean.length && prefixIdx + i < pageClean.length; i++) {
              if (pageClean[prefixIdx + i] === sourceClean[i]) matchLen++;
              else break;
            }
            for (let i = prefixIdx; i < prefixIdx + matchLen && i < charToSpan.length; i++) {
              matchedSpanSet.add(charToSpan[i]);
            }
          }
        }

        // Approach 3: sentence-level phrase matching
        if (matchedSpanSet.size === 0) {
          const phrases = source.text.split(/[.\n。,]/).map(p => normalize(p)).filter(p => p.length >= 6);
          for (const phrase of phrases) {
            let idx = -1;
            while ((idx = pageClean.indexOf(phrase, idx + 1)) !== -1) {
              for (let i = idx; i < idx + phrase.length && i < charToSpan.length; i++) {
                matchedSpanSet.add(charToSpan[i]);
              }
            }
          }
        }

        // Approach 4: sliding window (8→4 char fragments)
        if (matchedSpanSet.size === 0) {
          for (let wl = 8; wl >= 4; wl--) {
            for (let w = 0; w + wl <= sourceClean.length; w++) {
              const frag = sourceClean.slice(w, w + wl);
              let idx = -1;
              while ((idx = pageClean.indexOf(frag, idx + 1)) !== -1) {
                for (let i = idx; i < idx + wl && i < charToSpan.length; i++) {
                  matchedSpanSet.add(charToSpan[i]);
                }
              }
            }
            if (matchedSpanSet.size > 0) break;
          }
        }

        // Approach 5: raw text substring matching (bypass normalize entirely)
        if (matchedSpanSet.size === 0) {
          const sourceRaw = source.text.replace(/\s+/g, '');
          for (let si = 0; si < spans.length; si++) {
            const spanRaw = spans[si].text.replace(/\s+/g, '');
            if (spanRaw.length >= 3 && sourceRaw.includes(spanRaw)) {
              matchedSpanSet.add(si);
            }
          }
        }

        // Approach 6: individual character overlap (last resort)
        if (matchedSpanSet.size === 0) {
          const sourceChars = new Set(sourceClean.split(''));
          for (let si = 0; si < spans.length; si++) {
            for (const ch of normalize(spans[si].text)) {
              if (sourceChars.has(ch)) { matchedSpanSet.add(si); break; }
            }
          }
        }

        ctx.fillStyle = 'rgba(255, 200, 0, 0.3)';
        for (const si of matchedSpanSet) {
          const s = spans[si];
          ctx.fillRect(s.x, s.y, s.w, s.h);
        }
        ctx.lineWidth = 0;
      } catch (e) {
        console.warn('PDF page render failed:', e);
      }
    };
    render();
    return () => { cancelled = true; };
  }, [source.pdf, source.page_number, source.text, sessionId]);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-[95%] max-h-[90vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <span className="text-sm font-semibold">{source.pdf} — p.{source.page_number}</span>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex border-b bg-gray-50">
          {(['pdf', 'text'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === tab ? 'text-primary border-b-2 border-primary bg-white' : 'text-text-muted hover:text-text-secondary'}`}
            >
              {tab === 'pdf' ? 'PDF' : '텍스트'}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto bg-gray-100 flex justify-center p-4">
          <div className={`relative inline-block ${activeTab === 'pdf' ? '' : 'hidden'}`}>
            <canvas ref={canvasRef} className="shadow-lg rounded" />
          </div>
          <pre className={`w-full text-sm leading-relaxed whitespace-pre-wrap text-text-primary font-sans bg-white p-4 rounded-lg shadow-sm ${activeTab === 'text' ? '' : 'hidden'}`}>
            {source.text}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default function ChatBubble({ message }: Props) {
  const [popupSource, setPopupSource] = useState<PopupSource | null>(null);
  const isAI = message.role === 'ai';

  return (
    <>
      <div className={`flex items-start gap-3 ${isAI ? '' : 'justify-end'}`}>
        {isAI && (
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
            </svg>
          </div>
        )}
        <div className={`flex-1 min-w-0 ${isAI ? '' : 'flex justify-end'}`}>
          <div className={`p-4 max-w-[90%] rounded-2xl ${isAI ? 'bg-white border border-border' : 'bg-primary text-white'}`}>
            {message.isLoading ? (
              <div className="flex items-center gap-2 text-text-muted">
                <div className="w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin" />
                <span className="text-sm">{message.content || '문서를 검색 중...'}</span>
              </div>
            ) : (
              <div
                className={`text-sm leading-relaxed ${isAI ? 'text-text-primary' : 'text-white'}`}
                dangerouslySetInnerHTML={{ __html: message.content.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/^사용출처:.*$/gm, '').replace(/\n/g, '<br/>') }}
              />
            )}
            {isAI && message.sources && message.sources.length > 0 && (
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  <span className="text-xs text-text-muted mr-1">출처:</span>
                  {message.sources.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => setPopupSource(s)}
                      className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full hover:bg-primary/20 transition-colors cursor-pointer"
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      {s.pdf} · p.{s.page_number}
                    </button>
                  ))}
                </div>
                <details className="group">
                  <summary className="text-xs text-text-muted cursor-pointer hover:text-text-secondary transition-colors flex items-center gap-1">
                    <svg className="w-3 h-3 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                    참고한 문서 원본 문장
                  </summary>
                  <div className="mt-2 space-y-2">
                    {message.sources.map((s, i) => (
                      <div key={i} className="text-xs leading-relaxed bg-gray-50 border border-border/50 rounded-lg px-3 py-2">
                        <span className="text-primary font-medium">[{i + 1}] {s.pdf} · p.{s.page_number}</span>
                        <p className="text-text-secondary mt-1 whitespace-pre-wrap">{s.text}</p>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}
          </div>
        </div>
        {!isAI && (
          <div className="w-8 h-8 rounded-full bg-border flex items-center justify-center shrink-0 text-text-muted text-xs font-bold">
            신
          </div>
        )}
      </div>

      {popupSource && (
        <ChunkPopup
          source={popupSource}
          onClose={() => setPopupSource(null)}
        />
      )}
    </>
  );
}
