import { useState, useEffect } from 'react';
import { useAppStore } from '../store/useAppStore';

interface SearchBarProps {
  onSearch: (query: string, maxResults: number, smartSearch: boolean) => void;
  isLoading: boolean;
  initialQuery?: string | null;
  onQueryConsumed?: () => void;
  totalTables?: number;
}

const SUGGESTIONS = [
  '사업성 평가 결과',
  '정리 재구조화',
  'PF대출 연체율',
  '금융권 지원',
  '부동산 PF 현황',
];

const RECOMMENDED_QUESTIONS = [
  '부채비율 추이는?',
  'PF대출 연체율',
  '금융권 지원 현황',
];

export default function SearchBar({ onSearch, isLoading, initialQuery, onQueryConsumed, totalTables = 0 }: SearchBarProps) {
  const pdfs = useAppStore((s) => s.pdfs);
  const selectedPdfs = useAppStore((s) => s.selectedPdfs);
  const setSelectedPdfs = useAppStore((s) => s.setSelectedPdfs);
  const [query, setQuery] = useState('');
  const [useSmart, setUseSmart] = useState(false);
  const [maxResults, setMaxResults] = useState(5);

  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery);
      onQueryConsumed?.();
      if (!isLoading) {
        onSearch(initialQuery, maxResults, useSmart);
      }
    }
  }, [initialQuery]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;
    onSearch(query.trim(), maxResults, useSmart);
  };

  const handleSuggestion = (text: string) => {
    setQuery(text);
    onSearch(text, maxResults, useSmart);
  };

  const togglePdf = (name: string) => {
    if (selectedPdfs.includes(name)) {
      setSelectedPdfs(selectedPdfs.filter((n) => n !== name));
    } else {
      setSelectedPdfs([...selectedPdfs, name]);
    }
  };

  const allSelected = pdfs.length > 0 && selectedPdfs.length === pdfs.length;

  return (
    <div className="bg-surface-elevated border border-border rounded-xl p-5 shadow-sm">
      <form onSubmit={handleSubmit}>
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="검색어를 입력하세요..."
              className="w-full pl-11 pr-4 py-3 bg-surface border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all text-sm"
              disabled={isLoading}
            />
          </div>
          <button
            type="submit"
            disabled={!query.trim() || isLoading}
            className="px-6 py-3 bg-primary text-white rounded-lg font-medium text-sm hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-sm hover:shadow-md active:scale-[0.98]"
          >
            {isLoading ? (
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

        <div className="flex items-center gap-5 mt-4">
          <label className="flex items-center gap-2 cursor-pointer select-none group">
            <div className="relative">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={() => setSelectedPdfs(allSelected ? [] : pdfs.map((p) => p.name))}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-gray-200 rounded-full peer peer-checked:bg-primary transition-colors" />
              <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow-sm peer-checked:translate-x-4 transition-transform" />
            </div>
            <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors">검색할 PDF</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer select-none group">
            <div className="relative">
              <input
                type="checkbox"
                checked={useSmart}
                onChange={(e) => setUseSmart(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-gray-200 rounded-full peer peer-checked:bg-primary transition-colors" />
              <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow-sm peer-checked:translate-x-4 transition-transform" />
            </div>
            <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors">
              <span className="inline-block mr-0.5">🧠</span> Smart Search
              <span className="relative ml-1 group/info inline-flex">
                <span className="cursor-help text-text-muted text-xs">ℹ️</span>
                <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 w-48 px-2 py-1.5 bg-gray-800 text-white text-xs rounded-lg opacity-0 group-hover/info:opacity-100 transition-opacity pointer-events-none z-50">
                  AI가 검색된 여러 표 중 가장 관련성 높은 표 하나를 자동으로 선택해 보여줍니다.
                </span>
              </span>
            </span>
          </label>

          <div className="flex items-center gap-2 ml-auto">
            <span className="text-sm text-text-secondary">최대 결과:</span>
            <input
              type="range"
              min={1}
              max={20}
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              className="w-20 accent-primary"
            />
            <span className="text-sm font-medium text-primary w-6 text-right">{maxResults}</span>
          </div>
        </div>

        {pdfs.length > 1 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {pdfs.map((pdf) => {
              const checked = selectedPdfs.includes(pdf.name);
              return (
                <label
                  key={pdf.name}
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full cursor-pointer border transition-colors ${
                    checked
                      ? 'bg-primary/10 border-primary/30 text-primary'
                      : 'bg-surface border-border text-text-muted hover:text-text-secondary hover:border-primary/20'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => togglePdf(pdf.name)}
                    className="sr-only"
                  />
                  <span className="truncate max-w-[160px]">{pdf.name}</span>
                  <span className="text-[10px] opacity-60">{pdf.table_count}개</span>
                </label>
              );
            })}
          </div>
        )}
      </form>

      <div className="flex items-center justify-between mt-4">
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((text) => (
            <button
              key={text}
              onClick={() => handleSuggestion(text)}
              disabled={isLoading}
              className="px-3 py-1.5 text-xs bg-surface border border-border text-text-secondary rounded-full hover:bg-primary-light hover:text-primary hover:border-primary/30 disabled:opacity-40 transition-all active:scale-[0.97]"
            >
              {text}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 shrink-0 ml-3">
          {totalTables > 0 && (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-gradient-to-r from-orange-500 to-red-500 text-white rounded">
                HOT
              </span>
              <span className="text-xs text-text-muted whitespace-nowrap">
                총 {totalTables.toLocaleString()}개 표 인덱싱 완료
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-2 mt-3 overflow-x-auto pb-1">
        <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider shrink-0 self-center mr-1">추천</span>
        {RECOMMENDED_QUESTIONS.map((text) => (
          <button
            key={text}
            onClick={() => handleSuggestion(text)}
            disabled={isLoading}
            className="px-3 py-1.5 text-xs bg-primary/5 border border-primary/15 text-primary rounded-full hover:bg-primary/10 hover:border-primary/30 disabled:opacity-40 transition-all whitespace-nowrap active:scale-[0.97] flex items-center gap-1"
          >
            <svg className="w-3 h-3 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
