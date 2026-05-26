import { useState, useEffect, useRef, useMemo } from 'react';
import type { TableGroupSuggestion } from '../types';
import { useAppStore } from '../store/useAppStore';
import { BASE, confirmTableGroups } from '../api/client';

declare global {
  var pdfjsLib: any;
}

function mergeChainHtml(tableHtmls: string[]): string | null {
  if (tableHtmls.length === 0 || !tableHtmls[0]) return null;
  const parser = new DOMParser();
  const docFirst = parser.parseFromString(tableHtmls[0], 'text/html');
  const baseTable = docFirst.querySelector('table');
  if (!baseTable) return null;

  let tbody = baseTable.querySelector('tbody');
  if (!tbody) {
    tbody = docFirst.createElement('tbody');
    Array.from(baseTable.querySelectorAll(':scope > tr')).forEach(r => tbody!.appendChild(r));
    baseTable.appendChild(tbody);
  }

  for (let i = 1; i < tableHtmls.length; i++) {
    if (!tableHtmls[i]) continue;
    const docNext = parser.parseFromString(tableHtmls[i], 'text/html');
    const nextTable = docNext.querySelector('table');
    if (!nextTable) continue;

    const rows = Array.from(nextTable.querySelectorAll('tr'));
    for (const row of rows) {
      const cells = Array.from(row.querySelectorAll('th, td'));
      const isHeader = cells.length > 0 && cells.every(c => c.tagName === 'TH' && c.textContent?.trim());
      if (isHeader) continue;
      tbody.appendChild(docFirst.adoptNode(row.cloneNode(true)));
    }
  }

  return baseTable.outerHTML;
}

interface Props {
  suggestions: TableGroupSuggestion[];
  onComplete: () => void;
}

function PagePreview({
  pdfName,
  pageNumber,
  bbox,
  label,
  tableId,
  renderKey,
}: {
  pdfName: string;
  pageNumber: number;
  bbox: number[];
  label: string;
  tableId?: string;
  renderKey: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderTaskRef = useRef<any>(null);
  const sessionId = useAppStore((s) => s.sessionId);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let cancelled = false;

    const doRender = async () => {
      if (!window.pdfjsLib) {
        await new Promise<void>((r) => {
          const c = () => { window.pdfjsLib ? r() : setTimeout(c, 100); };
          c();
        });
        if (!window.pdfjsLib || cancelled) return;
      }
      const pdfjs = window.pdfjsLib;
      if (!pdfjs.GlobalWorkerOptions.workerSrc) {
        pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.0.379/build/pdf.worker.min.mjs';
      }
      const url = `${BASE}/documents/pdf?name=${encodeURIComponent(pdfName)}&session_id=${encodeURIComponent(sessionId)}`;
      try {
        const pdf = await pdfjs.getDocument(url).promise;
        if (cancelled) return;
        const page = await pdf.getPage(pageNumber);
        if (cancelled) return;
        const baseViewport = page.getViewport({ scale: 1.0 });
        const s = Math.min(250 / baseViewport.width, 300 / baseViewport.height);
        const viewport = page.getViewport({ scale: s });
        if (!canvasRef.current || cancelled) return;
        canvasRef.current.width = viewport.width;
        canvasRef.current.height = viewport.height;
        const renderTask = page.render({ canvasContext: ctx, viewport });
        renderTaskRef.current = renderTask;
        await renderTask.promise;
        if (cancelled) return;
        renderTaskRef.current = null;

        if (bbox && bbox.length === 4) {
          const [vx1, vy1] = viewport.convertToViewportPoint(bbox[0], bbox[3]);
          const [vx2, vy2] = viewport.convertToViewportPoint(bbox[2], bbox[1]);
          const hx = Math.min(vx1, vx2), hy = Math.min(vy1, vy2);
          const hw = Math.abs(vx2 - vx1), hh = Math.abs(vy2 - vy1);
          ctx.fillStyle = 'rgba(59, 130, 246, 0.25)';
          ctx.strokeStyle = 'rgba(59, 130, 246, 0.8)';
          ctx.lineWidth = 2;
          ctx.fillRect(hx, hy, hw, hh);
          ctx.strokeRect(hx, hy, hw, hh);
          ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
          ctx.font = '9px sans-serif';
          const tw = ctx.measureText(tableId || '').width;
          ctx.fillRect(hx, hy - 12, tw + 6, 12);
          ctx.fillStyle = '#fff';
          ctx.fillText(tableId || '', hx + 3, hy - 2);
        }
      } catch (e: any) {
        if (e?.name !== 'RenderingCancelledException') console.warn('Page render failed:', e);
      }
    };

    doRender();
    return () => {
      cancelled = true;
      if (renderTaskRef.current) { renderTaskRef.current.cancel(); renderTaskRef.current = null; }
    };
  }, [renderKey, pdfName, pageNumber, sessionId]);

  return (
    <div className="flex flex-col items-center">
      <span className="text-xs font-medium text-text-secondary mb-1">{label}</span>
      <canvas ref={canvasRef} className="rounded border border-border shadow-sm" />
    </div>
  );
}

export default function TableGroupSuggestionPopup({ suggestions, onComplete }: Props) {
  const [idx, setIdx] = useState(0);
  const [confirmed, setConfirmed] = useState<TableGroupSuggestion[]>([]);
  const [rejected, setRejected] = useState<TableGroupSuggestion[]>([]);
  const [phase, setPhase] = useState<'compare' | 'preview'>('compare');
  const sessionId = useAppStore((s) => s.sessionId);

  const current = suggestions[idx];
  const total = suggestions.length;

  const mergedHtml = useMemo(() => {
    if (!current?.tables) return null;
    return mergeChainHtml(current.tables.map(t => t.table_html));
  }, [current]);

  if (!current) return null;

  const chainLabel = current.tables.map(t => `p.${t.page_number}`).join(' → ');

  const goToNext = async (confirmedList: TableGroupSuggestion[], rejectedList: TableGroupSuggestion[]) => {
    const nextUnchecked = suggestions.findIndex((s, i) =>
      i > idx && !confirmedList.includes(s) && !rejectedList.includes(s)
    );
    if (nextUnchecked !== -1) {
      setIdx(nextUnchecked);
      setPhase('compare');
    } else if (confirmedList.length > 0) {
      try {
        await confirmTableGroups(
          current.pdf_name,
          confirmedList.map(c => ({
            group_id: c.group_id,
            table_ids: c.tables.map(t => t.table_id),
          })),
          rejectedList.map(r => ({
            group_id: r.group_id,
            table_ids: r.tables.map(t => t.table_id),
          })),
          sessionId,
        );
      } catch (e) {
        console.error('Failed to confirm table groups:', e);
      }
      onComplete();
    } else {
      onComplete();
    }
  };

  const handleSameTable = () => setPhase('preview');

  const handleMergeConfirm = async () => {
    const newConfirmed = [...confirmed, current];
    setConfirmed(newConfirmed);
    await goToNext(newConfirmed, rejected);
  };

  const handleMergeCancel = () => setPhase('compare');

  const handleDifferentTable = async () => {
    const newRejected = [...rejected, current];
    setRejected(newRejected);
    await goToNext(confirmed, newRejected);
  };

  const handleClose = () => {
    setRejected([...rejected, ...suggestions.slice(idx)]);
    onComplete();
  };

  const getStatus = (i: number): 'current' | 'done' | 'pending' => {
    if (i === idx) return 'current';
    if (confirmed.includes(suggestions[i]) || rejected.includes(suggestions[i])) return 'done';
    return 'pending';
  };

  const colsBadge = (s: TableGroupSuggestion, isActive: boolean) => {
    const allSame = s.same_cols;
    const label = allSame ? `${s.pair_cols[0]?.[1]}열` : s.pair_cols.map(([, a, b]) => `${a}≠${b}`).join(', ');
    const cls = isActive ? 'bg-blue-500 text-blue-100' : allSame ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700';
    return <span className={`ml-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${cls}`}>{label}</span>;
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-2xl max-w-5xl w-[95%] max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b bg-blue-50">
          <div>
            <h3 className="text-sm font-semibold text-blue-900">
              다중 페이지 표 확인
              <span className="ml-2 px-2 py-0.5 bg-blue-100 rounded-full text-xs font-normal text-blue-700">
                {confirmed.length + rejected.length} / {total} 완료
              </span>
            </h3>
            <p className="text-xs text-blue-700 mt-0.5">
              {phase === 'preview' ? '병합 결과를 확인해주세요.' : `${current.tables.length}개 표가 연속인지 확인해주세요.`}
            </p>
          </div>
          <button onClick={handleClose} className="text-text-muted hover:text-text-primary">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex gap-1 px-4 py-2 border-b bg-gray-50 overflow-x-auto">
          {suggestions.map((s, i) => {
            const status = getStatus(i);
            const isActive = i === idx;
            return (
              <button
                key={s.group_id}
                onClick={() => { setIdx(i); setPhase('compare'); }}
                className={`
                  flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors
                  ${isActive ? 'bg-blue-600 text-white shadow-sm' : ''}
                  ${status === 'done' && !isActive ? 'bg-green-50 text-green-700 border border-green-200' : ''}
                  ${status === 'pending' && !isActive ? 'bg-white text-text-secondary border border-border hover:bg-gray-100' : ''}
                `}
              >
                {status === 'done' && (
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
                {status === 'pending' && <span className="w-3.5 h-3.5 rounded-full border-2 border-gray-300" />}
                {s.tables.map(t => `p.${t.page_number}`).join('→')}
                {colsBadge(s, isActive)}
              </button>
            );
          })}
        </div>

        <div className="p-4 space-y-3 overflow-y-auto flex-1">
          {phase === 'compare' ? (
            <div className="flex items-center gap-4 justify-center flex-wrap">
              {current.tables.map((t, ti) => (
                <div key={t.table_id} className="flex items-center gap-4">
                  {ti > 0 && (
                    <div className="flex flex-col items-center gap-1">
                      <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                      </svg>
                      <span className="text-[10px] text-text-muted">
                        {current.pair_cols[ti - 1]?.[0] ? '=' : '≠'}
                      </span>
                    </div>
                  )}
                  <PagePreview
                    renderKey={`${t.table_id}-${idx}-compare`}
                    pdfName={current.pdf_name}
                    pageNumber={t.page_number}
                    bbox={t.bounding_box}
                    tableId={t.table_id}
                    label={`p.${t.page_number} — ${t.table_title || '표'}`}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-4 justify-center flex-wrap">
                {current.tables.map((t, ti) => (
                  <div key={t.table_id} className="flex items-center gap-4">
                    {ti > 0 && (
                      <div className="flex flex-col items-center gap-1">
                        <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        <span className="text-[10px] text-green-600 font-medium">병합</span>
                      </div>
                    )}
                    <PagePreview
                      renderKey={`${t.table_id}-${idx}-preview`}
                      pdfName={current.pdf_name}
                      pageNumber={t.page_number}
                      bbox={t.bounding_box}
                      tableId={t.table_id}
                      label={`p.${t.page_number} — ${t.table_title || '표'}`}
                    />
                  </div>
                ))}
              </div>
              <div className="border border-blue-200 rounded-lg overflow-hidden">
                <div className="px-3 py-2 bg-blue-50 text-xs font-medium text-blue-800">
                  병합 결과 미리보기 ({chainLabel})
                </div>
                <div className="overflow-auto max-h-64">
                  {mergedHtml ? (
                    <iframe
                      srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:8px;font-family:system-ui,sans-serif;font-size:12px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d1d5db;padding:4px 8px;text-align:left;vertical-align:middle}th{background:#f3f4f6;font-weight:600}tr:nth-child(even) td{background:#f9fafb}td table{width:100%;border-collapse:collapse;margin:2px 0;font-size:11px;background:#fff;border:1px solid #93c5fd;border-radius:4px;overflow:hidden}td table th{background:#eff6ff;font-weight:600;font-size:11px;padding:3px 6px;border:1px solid #93c5fd;color:#1e40af}td table td{padding:3px 6px;border:1px solid #dbeafe;font-size:11px;background:#fafbff}td table tr:nth-child(even) td{background:#f0f4ff}</style></head><body>${mergedHtml}</body></html>`}
                      style={{ width: '100%', minHeight: '60px', height: '200px', border: 'none', display: 'block' }}
                      sandbox="allow-same-origin"
                    />
                  ) : (
                    <div className="px-3 py-4 text-xs text-text-muted text-center">미리보기를 생성할 수 없습니다.</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-5 py-3 border-t bg-gray-50">
          {phase === 'compare' ? (
            <>
              <button
                onClick={() => {
                  const lastDone = suggestions.findLastIndex((s, i) =>
                    i !== idx && (confirmed.includes(s) || rejected.includes(s))
                  );
                  if (lastDone !== -1) {
                    const s = suggestions[lastDone];
                    if (confirmed.includes(s)) setConfirmed(confirmed.filter(c => c !== s));
                    else setRejected(rejected.filter(r => r !== s));
                    setIdx(lastDone);
                    setPhase('compare');
                  }
                }}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-border text-text-secondary hover:bg-gray-100 transition-colors"
              >
                ← 이전
              </button>
              <div className="flex items-center gap-3">
                <button onClick={handleDifferentTable} className="px-4 py-2 text-sm font-medium rounded-lg border border-border text-text-secondary hover:bg-gray-100 transition-colors">
                  다른 표
                </button>
                <button onClick={handleSameTable} className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors">
                  같은 표 ▶
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="text-xs text-text-muted">병합 결과를 확인 후 확정하세요.</div>
              <div className="flex items-center gap-3">
                <button onClick={handleMergeCancel} className="px-4 py-2 text-sm font-medium rounded-lg border border-border text-text-secondary hover:bg-gray-100 transition-colors">
                  ← 돌아가기
                </button>
                <button onClick={handleMergeConfirm} className="px-4 py-2 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors">
                  병합 확정 ✓
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
