import type { ProgressEvent } from '../types';

interface ProgressBarProps {
  progress: ProgressEvent | null;
  isVisible: boolean;
}

const PHASE_LABELS: Record<string, string> = {
  pdf: 'PDF 변환',
  vector: '벡터 검색',
  ai: 'AI 분석',
  done: '완료',
};

export default function ProgressBar({ progress, isVisible }: ProgressBarProps) {
  if (!isVisible || !progress) return null;

  return (
    <div className="bg-surface-elevated border border-border rounded-xl p-5 shadow-sm fade-in">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-primary animate-pulse-soft" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span className="text-sm font-semibold text-text-primary">Smart Search 진행 중</span>
        </div>
        <span className="text-xs font-medium text-primary">{Math.round(progress.pct)}%</span>
      </div>

      <div className="w-full bg-surface rounded-full h-2 overflow-hidden mb-3">
        <div
          className="h-full bg-gradient-to-r from-primary to-accent rounded-full transition-all duration-500 ease-out"
          style={{ width: `${progress.pct}%` }}
        />
      </div>

      <div className="flex items-center gap-1">
        {Object.entries(PHASE_LABELS).map(([key, name], i) => {
          const phaseOrder = ['pdf', 'vector', 'ai', 'done'];
          const currentIdx = phaseOrder.indexOf(progress.phase);
          const thisIdx = i;
          const isComplete = thisIdx < currentIdx;
          const isCurrent = thisIdx === currentIdx;

          return (
            <div key={key} className="flex items-center gap-1">
              {i > 0 && (
                <div className={`w-6 h-px ${thisIdx <= currentIdx ? 'bg-primary' : 'bg-border'}`} />
              )}
              <div className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium transition-all ${
                isComplete ? 'bg-success/10 text-success' :
                isCurrent ? 'bg-primary/10 text-primary' :
                'bg-surface text-text-muted'
              }`}>
                {isComplete ? (
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : isCurrent ? (
                  <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                ) : (
                  <div className="w-3 h-3 rounded-full border border-border" />
                )}
                {name}
              </div>
            </div>
          );
        })}
      </div>

      {progress.message && (
        <p className="mt-2 text-xs text-text-muted">{progress.message}</p>
      )}
    </div>
  );
}
