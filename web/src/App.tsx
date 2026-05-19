import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProgressEvent } from './types';
import * as api from './api/client';
import { BASE } from './api/client';
import { useAppStore } from './store/useAppStore';
import Sidebar from './components/Sidebar';
import SearchBar from './components/SearchBar';
import SearchResults from './components/SearchResults';
import ProgressBar from './components/ProgressBar';
import MainScreen from './components/MainScreen';
import TabBar from './components/TabBar';
import SessionHeader from './components/SessionHeader';
import DocumentViewer from './components/DocumentViewer';
import CreditReviewView from './components/CreditReviewView';
import QAPanel from './components/QAPanel';

export default function App() {
  const sessionId = useAppStore((s) => s.sessionId);
  const pdfs = useAppStore((s) => s.pdfs);
  const totalTables = useAppStore((s) => s.totalTables);
  const results = useAppStore((s) => s.results);
  const smartResult = useAppStore((s) => s.smartResult);
  const searchTime = useAppStore((s) => s.searchTime);
  const isLoading = useAppStore((s) => s.isLoading);
  const error = useAppStore((s) => s.error);
  const activeTab = useAppStore((s) => s.activeTab);
  const addPdfs = useAppStore((s) => s.addPdfs);
  const removePdf = useAppStore((s) => s.removePdf);
  const setLoading = useAppStore((s) => s.setLoading);
  const setError = useAppStore((s) => s.setError);
  const setSearchResults = useAppStore((s) => s.setSearchResults);
  const selectedPdfs = useAppStore((s) => s.selectedPdfs);
  const setPdfs = useAppStore((s) => s.setPdfs);
  const setSession = useAppStore((s) => s.setSession);
  const setUploading = useAppStore((s) => s.setUploading);
  const restoreFromStorage = useAppStore((s) => s.restoreFromStorage);
  const reset = useAppStore((s) => s.reset);

  const did404Ref = useRef(false);

  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [showProgress, setShowProgress] = useState(false);
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);

  const handleCreateSession = useCallback(async () => {
    const name = prompt('새 세션 이름을 입력하세요') || '새 세션';
    try {
      const res = await fetch(`${BASE}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (data.session_id) {
        localStorage.setItem('pdftablesearch_session_id', data.session_id);
        window.location.reload();
      }
    } catch (e) {
      alert('세션 생성 실패');
    }
  }, []);

  useEffect(() => {
    if (!sessionId || did404Ref.current) return;
    let cancelled = false;
    api.listPdfs(sessionId).then((data) => {
      if (cancelled) return;
      const pdfList = data.pdfs.map((info) => ({
        name: info.name,
        table_count: info.table_count,
        page_count: info.page_count,
      }));
      setPdfs(pdfList, data.total_tables, data.total_pages);
      restoreFromStorage(sessionId);
    }).catch((err) => {
      if (cancelled) return;
      if (err instanceof Error) {
        const msg = err.message || String(err);
        if (msg.includes('404') || msg.includes('Session not found')) {
          did404Ref.current = true;
          setSession('', '');
          localStorage.removeItem('pdftablesearch_session_id');
          window.location.replace('/');
        }
      }
    });
    return () => { cancelled = true; };
  }, [sessionId, setPdfs, setSession, restoreFromStorage]);

  const handleUploadComplete = useCallback((_sid: string, pdfData: Record<string, { table_count: number; page_count: number }>, totalTables: number, totalPages: number) => {
    const pdfList = Object.entries(pdfData).map(([name, info]) => ({
      name,
      table_count: info.table_count,
      page_count: info.page_count,
    }));
    addPdfs(pdfList, totalTables, totalPages);
  }, [addPdfs]);

  const handleDeletePdf = useCallback(async (name: string) => {
    await api.deletePdf(name, sessionId);
    removePdf(name);
  }, [sessionId, removePdf]);

  const handleMainUpload = useCallback(async (files: FileList) => {
    const pdfFiles = Array.from(files).filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
    if (pdfFiles.length === 0) return;

    if (!sessionId) {
      if (confirm('새 세션을 만들어 시작할까요?')) {
        handleCreateSession();
      }
      return;
    }

    setUploading(true);
    try {
      const result = await api.uploadPdfs(pdfFiles, sessionId);
      handleUploadComplete(result.session_id, result.pdfs, result.total_tables, result.total_pages ?? 0);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('Session not found') || msg.includes('404')) {
        localStorage.removeItem('pdftablesearch_session_id');
        if (confirm('세션이 만료되었습니다. 새 세션을 만들어 시작할까요?')) {
          handleCreateSession();
        } else {
          window.location.reload();
        }
      } else {
        alert(msg || '업로드 실패');
      }
    } finally {
      setUploading(false);
    }
  }, [sessionId, handleUploadComplete, setUploading, handleCreateSession]);

  const handleSearch = useCallback(async (query: string, maxResults: number, useSmartSearch: boolean) => {
    setLoading(true);
    setError(null);
    setSearchResults([], null, 0);

    const startTime = performance.now();

    try {
      if (useSmartSearch) {
        setShowProgress(true);
        setProgress({ phase: 'pdf', message: 'PDF를 분석하고 있습니다...', pct: 5 });

        const firstPdf = pdfs[0]?.name ?? '';
        if (!firstPdf) {
          throw new Error('Smart Search를 사용하려면 PDF를 먼저 업로드하세요.');
        }

        const smartRes = await api.smartSearch(query, firstPdf, sessionId, (evt) => {
          setProgress(evt);
        });

        const elapsed = (performance.now() - startTime) / 1000;
        setSearchResults([], smartRes, elapsed);
        setShowProgress(false);
      } else {
        const searchRes = await api.search(query, maxResults, sessionId, selectedPdfs);
        const elapsed = (performance.now() - startTime) / 1000;
        setSearchResults(searchRes.results, null, elapsed);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '검색 중 오류가 발생했습니다.');
      setShowProgress(false);
    } finally {
      setLoading(false);
    }
  }, [pdfs, sessionId, selectedPdfs, setLoading, setError, setSearchResults]);

  const handleQueryConsumed = useCallback(() => {
    setPendingQuery(null);
  }, []);

  const renderContent = () => {
    switch (activeTab) {
      case 'main':
        return pdfs.length === 0 ? (
          <MainScreen onUpload={handleMainUpload} />
        ) : (
          <MainScreen onUpload={handleMainUpload} hasDocuments />
        );

      case 'document':
        return <DocumentViewer />;

      case 'search':
        return (
          <div className="max-w-4xl mx-auto space-y-6">
            <div className="flex items-end justify-between">
              <div>
                <h1 className="text-2xl font-bold text-text-primary tracking-tight">표 검색</h1>
                <p className="text-sm text-text-muted mt-1">PDF 문서에서 의미적으로 관련된 표를 검색합니다</p>
              </div>
              {pdfs.length > 0 && (
                <div className="flex items-center gap-3 text-sm text-text-muted mb-0.5">
                  <span className="flex items-center gap-1">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    {pdfs.length}개 문서
                  </span>
                  <span className="text-border">|</span>
                  <span className="flex items-center gap-1">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 14h18m-9-4v8m-7-4h14M4 6h16" />
                    </svg>
                    {totalTables}개 테이블
                  </span>
                </div>
              )}
            </div>

            <SearchBar
              onSearch={handleSearch}
              isLoading={isLoading}
              initialQuery={pendingQuery}
              onQueryConsumed={handleQueryConsumed}
              totalTables={totalTables}
            />

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

            <SearchResults
              results={results}
              smartResult={smartResult}
              timeSeconds={searchTime}
              sessionId={sessionId}
            />

            {!isLoading && results.length === 0 && !smartResult && !error && (
              <div className="text-center py-16">
                <svg className="w-16 h-16 mx-auto text-border mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-text-muted text-sm">PDF를 업로드하고 검색어를 입력하세요</p>
              </div>
            )}
          </div>
        );

      case 'qa':
        return <QAPanel />;

      case 'credit':
        return <CreditReviewView />;
    }
  };

  if (!sessionId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-surface px-6">
        <div className="w-20 h-20 bg-surface-elevated border border-border rounded-2xl flex items-center justify-center mb-6">
          <svg className="w-10 h-10 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-text-primary mb-2">PDF Intelligence Portal</h1>
        <p className="text-sm text-text-muted mb-8">AI 기반 문서 분석 & 질의응답을 시작하려면 세션을 만들어주세요</p>
        <button
          onClick={handleCreateSession}
          className="px-8 py-3 bg-primary text-white rounded-xl text-base font-medium hover:bg-primary-hover transition-colors shadow-lg shadow-primary/20"
        >
          새 세션 시작하기
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      <Sidebar
        sessionId={sessionId}
        pdfs={pdfs}
        totalTables={totalTables}
        onUploadComplete={handleUploadComplete}
        onDeletePdf={handleDeletePdf}
        onReset={reset}
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TabBar />
        <SessionHeader />

        <main className={`flex-1 overflow-hidden ${activeTab === 'document' || activeTab === 'qa' ? '' : 'overflow-y-auto p-6'}`}>
          {renderContent()}
        </main>
      </div>
    </div>
  );
}
