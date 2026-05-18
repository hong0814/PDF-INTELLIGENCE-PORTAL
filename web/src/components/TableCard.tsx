import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import type { TableResult } from '../types';
import type { Components } from 'react-markdown';
import { useAppStore } from '../store/useAppStore';
import * as api from '../api/client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const TABLE_STYLES = `
  body { margin: 0; padding: 8px; font-family: 'Pretendard','Noto Sans KR',system-ui,sans-serif; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; line-height: 1.4; }
  th, td { border: 1px solid #e2e8f0; padding: 6px 8px; text-align: left; vertical-align: middle; }
  th { background-color: #dbeafe; font-weight: 600; }
  tr:nth-child(even) td { background-color: #f8fafc; }
  p { margin: 0; padding: 0; }
`;

const QA_RECOMMENDED_QUESTIONS = [
  '3년 평균 성장률은?',
  '디스플레이 감소가 전체에 미친 영향?',
  '2024년 전체 매출 대비 반도체 비중?',
  '표의 가로축과 세로축을 변경해줘',
];

function TableIframe({ html, expanded }: { html: string; expanded: boolean }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(100);

  const srcdoc = useMemo(() =>
    `<!DOCTYPE html><html><head><meta charset="utf-8"><style>${TABLE_STYLES}</style></head><body>${html}</body></html>`,
    [html]
  );

  const handleLoad = useCallback(() => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc?.body) return;
    const h = doc.body.scrollHeight;
    setHeight(h);
  }, []);

  const maxH = expanded ? 600 : 200;
  const displayH = Math.min(height + 4, maxH);

  return (
    <div className="border-b border-border-light overflow-x-auto">
      <iframe
        ref={iframeRef}
        srcDoc={srcdoc}
        onLoad={handleLoad}
        style={{ width: '100%', minWidth: 'max-content', height: `${displayH}px`, border: 'none', display: 'block' }}
        sandbox="allow-same-origin"
      />
      {height > maxH && !expanded && (
        <div style={{ height: 32, marginTop: -32, background: 'linear-gradient(transparent, white)', position: 'relative', pointerEvents: 'none' }} />
      )}
    </div>
  );
}

function CopyableTable({ children, ...props }: React.ComponentPropsWithoutRef<'table'> & { node?: unknown }) {
  const [copied, setCopied] = useState(false);
  const tableRef = useRef<HTMLTableElement>(null);

  const handleCopy = useCallback(() => {
    const tableEl = tableRef.current;
    if (!tableEl) return;

    const rows = Array.from(tableEl.querySelectorAll('tr'));
    if (rows.length === 0) return;

    const lines = rows.map(row => {
      const cells = Array.from(row.querySelectorAll('th, td'));
      return '| ' + cells.map(c => c.textContent?.trim() ?? '').join(' | ') + ' |';
    });
    const colCount = rows[0]?.querySelectorAll('th, td').length ?? 0;
    const separator = '| ' + Array.from({ length: colCount }, () => '---').join(' | ') + ' |';
    const markdown = lines.length > 1
      ? lines[0] + '\n' + separator + '\n' + lines.slice(1).join('\n')
      : lines.join('\n');

    const doCopy = (text: string) => {
      try {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        textArea.style.top = '-9999px';
        document.body.appendChild(textArea);
        textArea.select();
        textArea.setSelectionRange(0, text.length);
        document.execCommand('copy');
        document.body.removeChild(textArea);
        return true;
      } catch {
        return false;
      }
    };

    const onSuccess = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    };

    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(markdown).then(onSuccess).catch(() => {
        if (doCopy(markdown)) onSuccess();
      });
    } else {
      if (doCopy(markdown)) onSuccess();
    }
  }, []);

  const handleDownloadCsv = useCallback(() => {
    const tableEl = tableRef.current;
    if (!tableEl) return;

    const rows = Array.from(tableEl.querySelectorAll('tr'));
    if (rows.length === 0) return;

    const csvLines = rows.map(row => {
      const cells = Array.from(row.querySelectorAll('th, td'));
      return cells.map(c => {
        const text = c.textContent?.trim() ?? '';
        if (text.includes(',') || text.includes('"') || text.includes('\n')) {
          return '"' + text.replace(/"/g, '""') + '"';
        }
        return text;
      }).join(',');
    });

    const bom = '\uFEFF';
    const csv = bom + csvLines.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `table_${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  return (
    <div className="relative group">
      <table ref={tableRef} {...props}>{children}</table>
      <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 flex items-center gap-1">
        <button
          onClick={handleDownloadCsv}
          className="px-2 py-1 text-xs bg-white border border-border rounded shadow-sm hover:bg-success/10 hover:border-success/30 transition-all flex items-center gap-1"
          title="CSV 다운로드"
        >
          <svg className="w-3 h-3 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          <span className="text-text-muted">CSV</span>
        </button>
        <button
          onClick={handleCopy}
          className="px-2 py-1 text-xs bg-white border border-border rounded shadow-sm hover:bg-primary-light transition-all flex items-center gap-1"
        >
          {copied ? (
            <>
              <svg className="w-3 h-3 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              <span className="text-success">복사됨</span>
            </>
          ) : (
            <>
              <svg className="w-3 h-3 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              <span className="text-text-muted">복사</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

const markdownComponents: Components = {
  table: CopyableTable as Components['table'],
};

interface TableCardProps {
  table: TableResult;
  index: number;
  isSmartPick: boolean;
  sessionId: string;
}

export default function TableCard({ table, index, isSmartPick, sessionId }: TableCardProps) {
  const tableQAs = useAppStore((s) => s.tableQAs);
  const addTableQA = useAppStore((s) => s.addTableQA);
  const updateTableQA = useAppStore((s) => s.updateTableQA);
  const qaList = tableQAs[table.table_id] || [];
  const [questionInput, setQuestionInput] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [showFullTable, setShowFullTable] = useState(false);
  const qaEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    if (qaEndRef.current) {
      qaEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [qaList.length]);

  useEffect(() => {
    const pendingItems = qaList.filter(item => !item.answer);
    if (!pendingItems.length) return;

    const poll = async () => {
      try {
        const data = await api.getQaResults(sessionId);
        for (const r of data.results) {
          if (!r.done) continue;
          const idx = qaList.findIndex(item => item.question === r.question && !item.answer);
          if (idx >= 0) {
            updateTableQA(table.table_id, idx, r.answer);
          }
        }
      } catch {}
    };

    poll();
    pollRef.current = setInterval(poll, 2000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [qaList, sessionId, table.table_id, updateTableQA]);

  const handleAsk = useCallback(async (q?: string) => {
    const question = q ?? questionInput;
    if (!question.trim() || isAsking) return;
    setQuestionInput('');
    setIsAsking(true);

    addTableQA(table.table_id, { question: question.trim(), answer: '' });
    const idx = (tableQAs[table.table_id] || []).length;

    try {
      const htmlContent = table.table_html ?? table.table_markdown ?? '';
      const title = table.table_title ?? `페이지 ${table.page_number}`;
      let accumulated = '';
      await api.askQuestion(question.trim(), htmlContent, title, sessionId, (token) => {
        accumulated += token;
        updateTableQA(table.table_id, idx, accumulated);
      });
    } catch (err) {
      updateTableQA(table.table_id, idx,
        `오류: ${err instanceof Error ? err.message : '답변을 가져올 수 없습니다.'}`
      );
    } finally {
      setIsAsking(false);
    }
  }, [questionInput, isAsking, table, sessionId, tableQAs, addTableQA, updateTableQA]);

  const handleDownload = useCallback((format: 'html' | 'csv') => {
    const htmlContent = table.table_html ?? '';
    const mdContent = table.table_markdown ?? '';

    if (!htmlContent && !mdContent) {
      alert('다운로드할 테이블 데이터가 없습니다.');
      return;
    }

    let blob: Blob;
    let filename: string;

    if (format === 'html') {
      const src = htmlContent || mdToHtmlTable(mdContent);
      const doc = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${table.table_id}</title><style>body{font-family:sans-serif;padding:20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;text-align:left}th{background:#f5f5f5}</style></head><body>${src}</body></html>`;
      blob = new Blob([doc], { type: 'text/html;charset=utf-8' });
      filename = `${table.table_id}.html`;
    } else {
      const csv = htmlContent ? htmlTableToCsv(htmlContent) : markdownToCsv(mdContent);
      blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
      filename = `${table.table_id}.csv`;
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [table]);

  const handleCopy = useCallback(() => {
    const htmlContent = table.table_html ?? '';
    if (!htmlContent) {
      alert('복사할 테이블 데이터가 없습니다.');
      return;
    }
    try {
      const textArea = document.createElement('textarea');
      textArea.value = htmlContent;
      textArea.style.position = 'fixed';
      textArea.style.left = '-9999px';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
    } catch {}
  }, [table]);

  const htmlTableToCsv = (html: string): string => {
    const rows: string[][] = [];
    const rowMatches = html.match(/<tr[^>]*>([\s\S]*?)<\/tr>/gi) ?? [];
    for (const rowHtml of rowMatches) {
      const cells = rowHtml.match(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi) ?? [];
      const row = cells.map(cell => {
        const text = cell
          .replace(/<br\s*\/?>/gi, '\n')
          .replace(/<[^>]+>/g, '')
          .replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'")
          .replace(/&nbsp;/g, ' ')
          .trim();
        const escaped = text.replace(/"/g, '""');
        return text.includes(',') || text.includes('"') || text.includes('\n') ? `"${escaped}"` : escaped;
      });
      if (row.length > 0) rows.push(row);
    }
    return rows.map(r => r.join(',')).join('\n');
  };

  const markdownToCsv = (md: string): string => {
    return md
      .split('\n')
      .filter(line => line.trim() && !line.match(/^\|[\s\-:|]+\|$/))
      .map(line =>
        line.split('|').slice(1, -1).map(cell => {
          const c = cell.trim().replace(/"/g, '""');
          return c.includes(',') || c.includes('"') || c.includes('\n') ? `"${c}"` : c;
        }).join(',')
      )
      .join('\n');
  };

  const mdToHtmlTable = (md: string): string => {
    const rows = md
      .split('\n')
      .filter(line => line.trim() && !line.match(/^\|[\s\-:|]+\|$/))
      .map(line => line.split('|').slice(1, -1).map(c => c.trim()));
    if (rows.length === 0) return '';
    const [header, ...body] = rows;
    const makeRow = (cells: string[], tag: string) =>
      `<tr>${cells.map(c => `<${tag}>${c}</${tag}>`).join('')}</tr>`;
    return `<table><thead>${makeRow(header, 'th')}</thead><tbody>${body.map(r => makeRow(r, 'td')).join('')}</tbody></table>`;
  };

  return (
    <div className={`bg-surface-elevated border rounded-xl shadow-sm hover:shadow-md transition-shadow slide-up ${isSmartPick ? 'border-primary/30 ring-1 ring-primary/10' : 'border-border'}`}>
      <div className="p-4 border-b border-border-light">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${isSmartPick ? 'bg-primary text-white' : 'bg-surface text-text-secondary border border-border'}`}>
              #{index + 1}
            </span>
            <h3 className="text-sm font-semibold text-text-primary truncate max-w-md">
              {table.table_title ?? `페이지 ${table.page_number} 표`}
            </h3>
            {isSmartPick && (
              <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-bold bg-gradient-to-r from-amber-400 to-orange-500 text-white rounded-full shadow-sm">
                <span className="mr-0.5">✦</span> Smart 선택
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4 mt-2 text-xs text-text-muted" />
      </div>

      {table.table_html && (
        <TableIframe html={table.table_html} expanded={showFullTable} />
      )}

      {!table.table_html && table.table_markdown && (
        <div className={`p-3 border-b border-border-light overflow-auto text-xs font-mono whitespace-pre-wrap ${showFullTable ? 'max-h-[600px]' : 'max-h-[200px]'}`}>
          {table.table_markdown}
        </div>
      )}

      <div className="p-3 flex items-center gap-2 border-b border-border-light">
        <button
          onClick={() => setShowFullTable(!showFullTable)}
          className="px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface rounded-md transition-colors border border-border"
        >
          {showFullTable ? '접기' : '펼치기'}
        </button>
        <button
          onClick={() => handleDownload('html')}
          className="px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface rounded-md transition-colors border border-border flex items-center gap-1"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          HTML
        </button>
        <button
          onClick={() => handleDownload('csv')}
          className="px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface rounded-md transition-colors border border-border flex items-center gap-1"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          CSV
        </button>
      </div>

      <div className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <h4 className="text-xs font-semibold text-text-secondary">이 표에 대한 질의응답</h4>
          <span className="inline-flex items-center px-1.5 py-0.5 text-[9px] font-bold bg-primary/10 text-primary rounded-full border border-primary/20">
            AI 심사역
          </span>
        </div>

        <div className="flex gap-1.5 overflow-x-auto pb-2 mb-3">
          {QA_RECOMMENDED_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => handleAsk(q)}
              disabled={isAsking}
              className="px-2.5 py-1 text-[11px] bg-primary/5 border border-primary/15 text-primary rounded-full hover:bg-primary/10 hover:border-primary/30 disabled:opacity-40 transition-all whitespace-nowrap active:scale-[0.97] flex items-center gap-1 shrink-0"
            >
              <svg className="w-3 h-3 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              {q}
            </button>
          ))}
        </div>

        {qaList.length > 0 && (
          <div className="space-y-3 mb-3">
            {qaList.map((qa, i) => (
              <div key={i} className="text-sm">
                <div className="flex items-start gap-2 mb-1.5">
                  <span className="shrink-0 w-5 h-5 bg-primary/10 text-primary rounded-full flex items-center justify-center text-xs font-bold">Q</span>
                  <p className="text-text-primary leading-relaxed pt-0.5">{qa.question}</p>
                </div>
                <div className="flex items-start gap-2 ml-0">
                  <span className="shrink-0 w-5 h-5 bg-success/10 text-success rounded-full flex items-center justify-center text-xs font-bold">A</span>
                  <div className="flex-1 bg-primary/5 border border-primary/10 rounded-lg p-3 text-text-secondary leading-relaxed markdown-answer overflow-x-auto">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{qa.answer}</ReactMarkdown>
                    {isAsking && i === qaList.length - 1 && !qa.answer && (
                      <span className="inline-block w-2 h-4 bg-primary/40 animate-pulse ml-0.5 align-middle" />
                    )}
                    {isAsking && i === qaList.length - 1 && qa.answer && (
                      <span className="inline-block w-0.5 h-4 bg-primary animate-pulse ml-0.5 align-middle" />
                    )}
                  </div>
                </div>
              </div>
            ))}
            <div ref={qaEndRef} />
          </div>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            value={questionInput}
            onChange={(e) => setQuestionInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAsk(); }}
            placeholder="이 테이블에 질문하기..."
            className="flex-1 px-3 py-2 bg-surface border border-border rounded-lg text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
            disabled={isAsking}
          />
          <button
            onClick={() => handleAsk()}
            disabled={!questionInput.trim() || isAsking}
            className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1.5 active:scale-[0.97]"
          >
            {isAsking ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
            질문
        </button>
        <button
          onClick={handleCopy}
          className="px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface rounded-md transition-colors border border-border flex items-center gap-1"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          복사
        </button>
      </div>
      </div>
    </div>
  );
}
