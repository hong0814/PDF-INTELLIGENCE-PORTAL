import type { TableResult, SmartSearchResponse } from '../types';
import TableCard from './TableCard';

interface SearchResultsProps {
  results: TableResult[];
  smartResult: SmartSearchResponse | null;
  timeSeconds: number;
  sessionId: string;
}

export default function SearchResults({ results, smartResult, timeSeconds, sessionId }: SearchResultsProps) {
  if (results.length === 0 && !smartResult) return null;

  const smartTableId = smartResult?.result?.table_id;
  const totalCount = smartResult ? 1 + (results.filter(r => r.table_id !== smartTableId).length) : results.length;

  return (
    <div className="space-y-4 fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-text-secondary">
            검색 결과
            <span className="ml-1.5 text-text-muted font-normal">
              ({totalCount}개)
            </span>
          </h2>
          {smartResult && (
            <span className="inline-flex items-center px-2.5 py-1 text-xs font-semibold bg-primary/10 text-primary rounded-full border border-primary/20">
              <span className="mr-1">🏆</span> AI가 선택한 테이블
            </span>
          )}
          <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-gradient-to-r from-orange-500 to-red-500 text-white rounded">
            HOT
          </span>
        </div>
        <div className="text-xs text-text-muted">
          {timeSeconds > 0 && (
            <span>검색 소요: {timeSeconds.toFixed(2)}초</span>
          )}
        </div>
      </div>

      {smartResult && (
        <TableCard
          table={smartResult.result}
          index={0}
          isSmartPick
          sessionId={sessionId}
        />
      )}

      {results
        .filter(r => r.table_id !== smartTableId)
        .map((table, i) => (
          <TableCard
            key={table.table_id}
            table={table}
            index={smartResult ? i + 1 : i}
            isSmartPick={false}
            sessionId={sessionId}
          />
        ))}
    </div>
  );
}
