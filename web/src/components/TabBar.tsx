import { type ReactNode, useMemo } from 'react';
import { useAppStore, type TabId } from '../store/useAppStore';

const TABS: { id: TabId; label: string; icon: ReactNode }[] = [
  {
    id: 'main',
    label: '메인',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    id: 'document',
    label: '문서 보기',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    id: 'search',
    label: '문서 검색',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 14h18m-9-4v8m-7-4h14M4 6h16" />
      </svg>
    ),
  },
  {
    id: 'translation',
    label: 'PDF 번역',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="m10.5 21 5.25-11.25L21 21m-9-3h7.5M3 5.621a48.474 48.474 0 0 1 6-.371m0 0c1.12 0 2.233.038 3.334.114M9 5.25V3m3.334 2.364C11.176 10.658 7.69 15.08 3 17.502m9.334-12.138c.896.061 1.785.147 2.666.257m-4.589 8.495a18.023 18.023 0 0 1-3.827-5.802" />
      </svg>
    ),
  },
  {
    id: 'credit',
    label: '기업금융심사',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
      </svg>
    ),
  },
];

export default function TabBar() {
  const activeTab = useAppStore((s) => s.activeTab);
  const setActiveTab = useAppStore((s) => s.setActiveTab);
  const tableQAs = useAppStore((s) => s.tableQAs);
  const unifiedFollowups = useAppStore((s) => s.unifiedFollowups);
  const isTranslating = useAppStore((s) => s.isTranslating);
  const isUnifiedSearchLoading = useAppStore((s) => s.isUnifiedSearchLoading);
  const hasSearchQA = useMemo(() => {
    for (const items of Object.values(tableQAs)) {
      if (items.some(item => !item.answer)) return true;
    }
    return false;
  }, [tableQAs]);

  const hasUnifiedFollowup = useMemo(() => {
    return unifiedFollowups.some(m => m.isLoading);
  }, [unifiedFollowups]);

  return (
    <nav className="flex items-center border-b border-border bg-surface-elevated px-4">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.id;
        const showPending = (tab.id === 'search' && (hasSearchQA || hasUnifiedFollowup || isUnifiedSearchLoading)) || (tab.id === 'translation' && isTranslating);
        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors relative
              ${isActive
                ? 'text-primary'
                : 'text-text-muted hover:text-text-secondary'
              }
            `}
          >
            {tab.icon}
            {tab.label}
            {showPending && (
              <span className="w-2 h-2 bg-accent rounded-full animate-pulse ml-0.5" />
            )}
            {isActive && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-t-full" />
            )}
          </button>
        );
      })}
    </nav>
  );
}
