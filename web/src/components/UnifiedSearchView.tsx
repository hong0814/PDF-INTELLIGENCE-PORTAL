import { useState, useCallback, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { useAppStore } from '../store/useAppStore';
import { drawPIIMasks } from '../utils/piiDetection';
import * as api from '../api/client';
import { BASE } from '../api/client';
import type { ProgressEvent, UnifiedSource, TableResult } from '../types';
import ProgressBar from './ProgressBar';

declare global { var pdfjsLib: any; }

export default function UnifiedSearchView() {
  const sessionId = useAppStore((s) => s.sessionId);
  const pdfs = useAppStore((s) => s.pdfs);
  const totalTables = useAppStore((s) => s.totalTables);
  const selectedPdfs = useAppStore((s) => s.selectedPdfs);
  const unifiedResult = useAppStore((s) => s.unifiedResult);
  const unifiedFollowups = useAppStore((s) => s.unifiedFollowups);
  const setUnifiedResult = useAppStore((s) => s.setUnifiedResult);
  const addUnifiedFollowup = useAppStore((s) => s.addUnifiedFollowup);
  const updateUnifiedFollowup = useAppStore((s) => s.updateUnifiedFollowup);
  const clearUnifiedSearch = useAppStore((s) => s.clearUnifiedSearch);
  const setSelectedPdfs = useAppStore((s) => s.setSelectedPdfs);
  const isUnifiedSearchLoading = useAppStore((s) => s.isUnifiedSearchLoading);
  const setIsUnifiedSearchLoading = useAppStore((s) => s.setIsUnifiedSearchLoading);

  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [showProgress, setShowProgress] = useState(false);
  const [popupSource, setPopupSource] = useState<UnifiedSource | null>(null);

  const [followupInput, setFollowupInput] = useState('');
  const [isFollowupLoading, setIsFollowupLoading] = useState(false);

  const resultRef = useRef<HTMLDivElement>(null);
  const followupEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    followupEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [unifiedFollowups]);

  const handleSearch = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed || !sessionId) return;

    setIsUnifiedSearchLoading(true);
    setError(null);
    setShowProgress(true);
    setProgress({ phase: 'search', message: '문서를 검색하고 있습니다...', pct: 10 });

    try {
      const result = await api.unifiedSearch(
        trimmed,
        sessionId,
        (evt: ProgressEvent) => setProgress(evt),
        selectedPdfs.length > 0 ? selectedPdfs : undefined,
      );
      setUnifiedResult(result);
      setShowProgress(false);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (err) {
      setError(err instanceof Error ? err.message : '검색 중 오류가 발생했습니다.');
      setShowProgress(false);
    } finally {
      setIsUnifiedSearchLoading(false);
    }
  }, [query, sessionId, selectedPdfs, setUnifiedResult]);

  const handleFollowup = useCallback(async () => {
    const trimmed = followupInput.trim();
    if (!trimmed || !unifiedResult || !sessionId) return;

    const userMsgId = `fu_${Date.now()}`;
    const aiMsgId = `fu_ai_${Date.now()}`;

    addUnifiedFollowup({ id: userMsgId, role: 'user', content: trimmed });
    addUnifiedFollowup({ id: aiMsgId, role: 'ai', content: '', isLoading: true });
    setFollowupInput('');
    setIsFollowupLoading(true);

    try {
      let accumulated = '';
      await api.unifiedFollowup(
        trimmed,
        unifiedResult.answer,
        JSON.stringify(unifiedResult.sources),
        sessionId,
        (token: string) => {
          accumulated += token;
          updateUnifiedFollowup(aiMsgId, { content: accumulated });
        },
      );
      updateUnifiedFollowup(aiMsgId, { isLoading: false });
    } catch (err) {
      updateUnifiedFollowup(aiMsgId, {
        content: `오류: ${err instanceof Error ? err.message : '답변 생성 실패'}`,
        isLoading: false,
      });
    } finally {
      setIsFollowupLoading(false);
    }
  }, [followupInput, unifiedResult, sessionId, addUnifiedFollowup, updateUnifiedFollowup]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSearch();
    }
  }, [handleSearch]);

  const handleFollowupKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleFollowup();
    }
  }, [handleFollowup]);

  const togglePdfFilter = useCallback((name: string) => {
    const current = selectedPdfs;
    const next = current.includes(name)
      ? current.filter((n) => n !== name)
      : [...current, name];
    setSelectedPdfs(next);
  }, [selectedPdfs, setSelectedPdfs]);

  const hasResult = !!unifiedResult || !!error;

  return (
    <div className="space-y-6">
      {hasResult ? (
        <>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-text-primary">검색 결과</h2>
              {query && (
                <span className="text-sm text-text-muted bg-surface-elevated border border-border rounded-full px-3 py-0.5 max-w-xs truncate">
                  {query}
                </span>
              )}
              {pdfs.length > 0 && (
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  <span className="bg-surface-elevated border border-border rounded-full px-2 py-0.5">{pdfs.length}개 문서</span>
                  <span className="bg-surface-elevated border border-border rounded-full px-2 py-0.5">{totalTables}개 테이블</span>
                </div>
              )}
            </div>
            <button
              onClick={() => { clearUnifiedSearch(); setQuery(''); }}
              className="flex items-center gap-1 text-xs text-text-muted hover:text-danger transition-colors px-2 py-1 rounded hover:bg-danger/10"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
              검색 초기화
            </button>
          </div>

          <div className="bg-surface-elevated border border-border rounded-xl p-4 space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="검색어를 입력하세요..."
                className="flex-1 bg-surface border border-border rounded-lg px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
                disabled={isUnifiedSearchLoading}
              />
              <button
                onClick={handleSearch}
                disabled={isUnifiedSearchLoading || !query.trim()}
                className="px-5 py-2.5 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shrink-0"
              >
                {isUnifiedSearchLoading ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                )}
                검색
              </button>
            </div>

            {pdfs.length > 1 && (
              <div className="flex flex-wrap gap-1.5">
                {pdfs.map((pdf) => (
                  <button
                    key={pdf.name}
                    onClick={() => togglePdfFilter(pdf.name)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                      selectedPdfs.includes(pdf.name)
                        ? 'bg-primary/10 text-primary border border-primary/30'
                        : 'bg-surface text-text-muted border border-border hover:border-primary/30'
                    }`}
                  >
                    {pdf.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="pt-16 pb-8">
          <div className="text-center mb-8">
            <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <svg className="w-7 h-7 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-text-primary mb-1">문서 검색</h2>
            <p className="text-sm text-text-muted">표와 텍스트를 통합 검색합니다. AI가 관련 문서를 찾아 답변합니다.</p>
          </div>

          <div className="bg-surface-elevated border border-border rounded-xl p-4 space-y-3 max-w-3xl mx-auto">
            <div className="flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="검색어를 입력하세요..."
                className="flex-1 bg-surface border border-border rounded-lg px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
                disabled={isUnifiedSearchLoading}
              />
              <button
                onClick={handleSearch}
                disabled={isUnifiedSearchLoading || !query.trim()}
                className="px-5 py-2.5 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shrink-0"
              >
                {isUnifiedSearchLoading ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                )}
                검색
              </button>
            </div>

            {pdfs.length > 1 && (
              <div className="flex flex-wrap gap-1.5">
                {pdfs.map((pdf) => (
                  <button
                    key={pdf.name}
                    onClick={() => togglePdfFilter(pdf.name)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                      selectedPdfs.includes(pdf.name)
                        ? 'bg-primary/10 text-primary border border-primary/30'
                        : 'bg-surface text-text-muted border border-border hover:border-primary/30'
                    }`}
                  >
                    {pdf.name}
                  </button>
                ))}
              </div>
            )}

            {pdfs.length > 0 && (
              <div className="flex items-center justify-center gap-3 pt-1">
                <span className="inline-flex items-center gap-1.5 text-xs text-text-muted bg-surface rounded-full px-3 py-1">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  {pdfs.length}개 문서
                </span>
                <span className="inline-flex items-center gap-1.5 text-xs text-text-muted bg-surface rounded-full px-3 py-1">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 14h18m-9-4v8m-7-4h14M4 6h16" />
                  </svg>
                  {totalTables}개 테이블
                </span>
              </div>
            )}
          </div>

          {!isUnifiedSearchLoading && pdfs.length === 0 && (
            <p className="text-center text-text-muted/60 text-xs mt-6">PDF를 업로드하면 표와 텍스트를 모두 검색할 수 있습니다</p>
          )}
        </div>
      )}

      <ProgressBar progress={progress} isVisible={showProgress} />

      {error && (
        <div className="bg-danger/5 border border-danger/20 rounded-xl p-4 flex items-start gap-3 fade-in">
          <svg className="w-5 h-5 text-danger shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-sm font-medium text-danger">오류 발생</p>
            <p className="text-sm text-danger/80 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {unifiedResult && (
        <div ref={resultRef} className="space-y-4 fade-in">
          <AnswerCard
            answer={unifiedResult.answer}
            tables={unifiedResult.tables}
            sources={unifiedResult.sources}
            onSourceClick={(src) => setPopupSource(src)}
          />

          {unifiedFollowups.length > 0 && (
            <div className="space-y-3">
              {unifiedFollowups.map((msg) => (
                <FollowupBubble key={msg.id} message={msg} onSourceClick={(src) => setPopupSource(src)} />
              ))}
            </div>
          )}

          <div className="bg-surface-elevated border border-border rounded-xl p-3 flex gap-2">
            <input
              type="text"
              value={followupInput}
              onChange={(e) => setFollowupInput(e.target.value)}
              onKeyDown={handleFollowupKeyDown}
              placeholder="결과에 대해 추가 질문하세요..."
              className="flex-1 bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
              disabled={isFollowupLoading}
            />
            <button
              onClick={handleFollowup}
              disabled={isFollowupLoading || !followupInput.trim()}
              className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              질문
            </button>
          </div>
        </div>
      )}

      {popupSource && (
        <SourcePopup source={popupSource} onClose={() => setPopupSource(null)} />
      )}
    </div>
  );
}

function AnswerCard({
  answer,
  tables,
  sources,
  onSourceClick,
}: {
  answer: string;
  tables: TableResult[];
  sources: UnifiedSource[];
  onSourceClick: (source: UnifiedSource) => void;
}) {
  const [showTables, setShowTables] = useState(true);
  const rawAnswer = answer.replace(/사용출처:.*$/m, '').trim();
  const cleanAnswer = rawAnswer.replace(/[\[【](텍스트출처|표출처)\d*[\]】]/g, (match) => {
    const isTable = match.includes('표출처');
    return `<span class="source-marker ${isTable ? 'source-marker-table' : 'source-marker-text'}">${match}</span>`;
  });

  return (
    <div className="bg-surface-elevated border border-border rounded-xl overflow-hidden">
      <div className="p-6 border-b border-border">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-text-primary">AI 답변</span>
        </div>
        <div className="markdown-answer text-sm leading-relaxed max-w-full overflow-x-auto">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{cleanAnswer}</ReactMarkdown>
        </div>
      </div>

      {tables.length > 0 && (
        <div className="border-b border-border">
          <button
            onClick={() => setShowTables(!showTables)}
            className="w-full px-6 py-3 flex items-center justify-between text-sm font-medium text-text-primary hover:bg-surface/50 transition-colors"
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 14h18m-9-4v8m-7-4h14M4 6h16" />
              </svg>
              관련 표 ({tables.length})
            </span>
            <svg className={`w-4 h-4 text-text-muted transition-transform ${showTables ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {showTables && (
            <div className="px-6 pb-4 space-y-3">
              {tables.map((table, i) => (
                <InlineTable key={table.table_id || i} table={table} />
              ))}
            </div>
          )}
        </div>
      )}

      {sources.length > 0 && (
        <div className="px-6 py-4">
          <p className="text-xs font-medium text-text-muted mb-2 flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m9.86-2.56a4.5 4.5 0 00-1.242-7.244l-4.5-4.5a4.5 4.5 0 00-6.364 6.364l1.757 1.757" />
            </svg>
            출처
          </p>
          <div className="flex flex-wrap gap-2">
            {sources.map((source, i) => (
              <SourceChip key={i} source={source} onClick={() => onSourceClick(source)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function InlineTable({ table }: { table: TableResult }) {
  const [expanded, setExpanded] = useState(false);
  const title = table.table_title || `표 (p.${table.page_number})`;

  const downloadCSV = useCallback(() => {
    const html = table.table_html || '';
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const rows = doc.querySelectorAll('tr');
    const csvLines: string[] = [];
    rows.forEach(row => {
      const cells = row.querySelectorAll('th, td');
      const vals = Array.from(cells).map(c => `"${(c.textContent || '').replace(/"/g, '""')}"`);
      csvLines.push(vals.join(','));
    });
    const bom = '\uFEFF';
    const blob = new Blob([bom + csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.replace(/[^가-힣a-zA-Z0-9]/g, '_')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [table.table_html, title]);

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="w-full px-3 py-2 flex items-center justify-between bg-surface">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-left flex-1 min-w-0 hover:opacity-80 transition-opacity"
        >
          <svg className={`w-3.5 h-3.5 text-text-muted shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
          <span className="text-xs font-medium text-text-primary truncate">{title}</span>
        </button>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          <button
            onClick={downloadCSV}
            className="p-1 rounded hover:bg-surface-elevated transition-colors"
            title="CSV 다운로드"
          >
            <svg className="w-3.5 h-3.5 text-text-muted hover:text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </button>
        </div>
      </div>
      {expanded && table.table_html && (
        <div className="border-t border-border">
          <iframe
            srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:Pretendard,system-ui,sans-serif;padding:12px;margin:0}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border:1px solid #e2e8f0;padding:6px 8px;text-align:left}th{background-color:#dbeafe;font-weight:600}tr:nth-child(even)td{background-color:#f8fafc}</style></head><body>${table.table_html}</body></html>`}
            className="w-full border-0"
            style={{ height: '300px' }}
            sandbox="allow-same-origin"
            title={title}
          />
        </div>
      )}
    </div>
  );
}

function SourceChip({ source, onClick }: { source: UnifiedSource; onClick: () => void }) {
  const isText = source.type === 'text';
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-surface border border-border hover:border-primary/30 hover:bg-primary/5 transition-colors"
    >
      <span className={`w-1.5 h-1.5 rounded-full ${isText ? 'bg-blue-400' : 'bg-green-400'}`} />
      <span className="text-text-secondary">{source.pdf}</span>
      <span className="text-text-muted">p.{source.page_number}</span>
      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${isText ? 'bg-blue-500/10 text-blue-400' : 'bg-green-500/10 text-green-400'}`}>
        {isText ? '텍스트' : '표'}
      </span>
    </button>
  );
}

function FollowupBubble({
  message,
  onSourceClick,
}: {
  message: { id: string; role: 'user' | 'ai'; content: string; sources?: UnifiedSource[]; isLoading?: boolean };
  onSourceClick: (source: UnifiedSource) => void;
}) {
  const isUser = message.role === 'user';
  const cleanContent = message.content.replace(/사용출처:.*$/m, '').trim();

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-xl px-4 py-3 ${
        isUser
          ? 'bg-primary text-white'
          : 'bg-surface-elevated border border-border'
      }`}>
        {message.isLoading && !message.content ? (
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        ) : isUser ? (
          <p className="text-sm">{message.content}</p>
        ) : (
          <div className="markdown-answer text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{cleanContent}</ReactMarkdown>
          </div>
        )}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-border">
            {message.sources.map((src, i) => (
              <SourceChip key={i} source={src} onClick={() => onSourceClick(src)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SourcePopup({ source, onClose }: { source: UnifiedSource; onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sessionId = useAppStore((s) => s.sessionId);
  const isTable = source.type === 'table';
  const [activeTab, setActiveTab] = useState<'pdf' | 'text' | 'table'>('pdf');
  const [tableHtml, setTableHtml] = useState<string>(source.merged_table_html || '');
  const [pdfRendered, setPdfRendered] = useState(false);

  useEffect(() => {
    if (!isTable || !source.table_id) return;
    if (source.merged_table_html) return;
    fetch(`${BASE}/documents/tables?name=${encodeURIComponent(source.pdf)}&session_id=${encodeURIComponent(sessionId)}`)
      .then(r => r.json())
      .then(data => {
        const tbl = (data.tables || []).find((t: any) => t.table_id === source.table_id);
        const html = tbl?.merged_table_html || tbl?.table_html;
        if (html) setTableHtml(html);
      })
      .catch(() => {});
  }, [isTable, source.table_id, source.pdf, sessionId, source.merged_table_html]);

  useEffect(() => {
    if (activeTab !== 'pdf') return;
    if (pdfRendered) return;
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

        if (source.type === 'table' && source.bounding_box && source.bounding_box.length >= 4) {
          const bbox = source.bounding_box;
          const [vx1, vy1] = viewport.convertToViewportPoint(bbox[0], bbox[3]);
          const [vx2, vy2] = viewport.convertToViewportPoint(bbox[2], bbox[1]);
          const hx = Math.min(vx1, vx2);
          const hy = Math.min(vy1, vy2);
          const hw = Math.abs(vx2 - vx1);
          const hh = Math.abs(vy2 - vy1);
          ctx.fillStyle = 'rgba(59, 130, 246, 0.25)';
          ctx.fillRect(hx, hy, hw, hh);
          ctx.strokeStyle = 'rgba(59, 130, 246, 0.8)';
          ctx.lineWidth = 2;
          ctx.strokeRect(hx, hy, hw, hh);
        }

        const allSpans: { text: string; x: number; y: number; w: number; h: number }[] = [];
        try {
          const tc = await page.getTextContent();
          for (const item of tc.items as any[]) {
            if (!item.str || !item.str.trim()) continue;
            const tx = pdfjs.Util.transform(viewport.transform, item.transform);
            const fontSize = Math.abs(tx[0]) || Math.abs(tx[3]) || 10;
            allSpans.push({
              text: item.str,
              x: tx[4],
              y: tx[5] - fontSize,
              w: (item.width || item.str.length * fontSize * 0.6) * scale,
              h: fontSize * 1.2,
            });
          }
        } catch (_) {}
        drawPIIMasks(canvas, allSpans);

        if (source.type === 'text' && source.text) {
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
              w: (item.width || item.str.length * fontSize * 0.6) * scale,
              h: fontSize * 1.2,
            });
          }

          const normalize = (s: string) => s.replace(/[\s\.,;:!?·•\-()\[\]{}<>\/\\'"~,=%&#@+\u00A0]+/g, '');
          const sourceClean = normalize(source.text);

          const matchedSpanSet = new Set<number>();

          if (sourceClean.length > 0 && spans.length > 0) {
            const charToSpan: number[] = [];
            let pageClean = '';
            for (let si = 0; si < spans.length; si++) {
              const clean = normalize(spans[si].text);
              for (let c = 0; c < clean.length; c++) charToSpan.push(si);
              pageClean += clean;
            }

            const fullIdx = pageClean.indexOf(sourceClean);
            if (fullIdx >= 0) {
              for (let i = fullIdx; i < fullIdx + sourceClean.length && i < charToSpan.length; i++) {
                matchedSpanSet.add(charToSpan[i]);
              }
            }

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

            if (matchedSpanSet.size === 0) {
              const sourceRaw = source.text.replace(/\s+/g, '');
              for (let si = 0; si < spans.length; si++) {
                const spanRaw = spans[si].text.replace(/\s+/g, '');
                if (spanRaw.length >= 3 && sourceRaw.includes(spanRaw)) {
                  matchedSpanSet.add(si);
                }
              }
            }
          }

          ctx.fillStyle = 'rgba(255, 200, 0, 0.3)';
          for (const si of matchedSpanSet) {
            const s = spans[si];
            ctx.fillRect(s.x, s.y, s.w, s.h);
          }
        }
        setPdfRendered(true);
      } catch (e) {
        console.warn('PDF page render failed:', e);
      }
    };
    render();
    return () => { cancelled = true; };
  }, [activeTab, source.pdf, source.page_number, source.text, sessionId, pdfRendered]);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-[95%] max-h-[90vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${source.type === 'text' ? 'bg-blue-500/10 text-blue-600' : 'bg-green-500/10 text-green-600'}`}>
              {source.type === 'text' ? '텍스트' : '표'}
            </span>
            <span className="text-sm font-semibold">{source.pdf} — p.{source.page_number}</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex border-b bg-gray-50">
          {([
            ...(isTable ? ['table' as const] : []),
            'pdf' as const,
            ...(!isTable ? ['text' as const] : []),
          ]).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === tab ? 'text-blue-600 border-b-2 border-blue-600 bg-white' : 'text-gray-500 hover:text-gray-700'}`}
            >
              {tab === 'pdf' ? 'PDF' : tab === 'text' ? '텍스트' : '표 내용'}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto bg-gray-100 p-4">
          {isTable && activeTab === 'table' && (
            <div className="bg-white rounded-lg shadow-sm overflow-auto">
              {tableHtml ? (
              <iframe
                srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:Pretendard,system-ui,sans-serif;padding:12px;margin:0}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border:1px solid #e2e8f0;padding:6px 8px;text-align:left}th{background-color:#dbeafe;font-weight:600}tr:nth-child(even) td{background-color:#f8fafc}</style></head><body>${tableHtml}</body></html>`}
                className="w-full border-0"
                sandbox="allow-same-origin"
                style={{ minHeight: '200px' }}
                onLoad={(e) => {
                  const iframe = e.target as HTMLIFrameElement;
                  iframe.style.height = (iframe.contentDocument?.body?.scrollHeight ?? 200) + 'px';
                }}
              />
              ) : (
                <div className="flex items-center justify-center py-12 text-sm text-gray-400">
                  <svg className="w-4 h-4 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  표 내용 로딩 중...
                </div>
              )}
            </div>
          )}
          <div className={`flex justify-center ${activeTab === 'pdf' ? '' : 'hidden'}`}>
            <canvas ref={canvasRef} className="shadow-lg rounded" />
          </div>
          <pre className={`text-sm leading-relaxed whitespace-pre-wrap text-gray-800 font-sans bg-white p-4 rounded-lg shadow-sm ${activeTab === 'text' ? '' : 'hidden'}`}>
            {source.text}
          </pre>
        </div>
      </div>
    </div>
  );
}
