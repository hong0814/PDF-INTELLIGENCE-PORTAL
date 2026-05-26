import { useCallback, useEffect, useRef, useState } from 'react';
import type { TableGroupSuggestion } from './types';
import * as api from './api/client';
import { BASE } from './api/client';
import { useAppStore } from './store/useAppStore';
import Sidebar from './components/Sidebar';
import MainScreen from './components/MainScreen';
import TabBar from './components/TabBar';
import SessionHeader from './components/SessionHeader';
import DocumentViewer from './components/DocumentViewer';
import CreditReviewView from './components/CreditReviewView';
import UnifiedSearchView from './components/UnifiedSearchView';
import TranslationView from './components/TranslationView';
import TableGroupSuggestionPopup from './components/TableGroupSuggestionPopup';

export default function App() {
  const sessionId = useAppStore((s) => s.sessionId);
  const pdfs = useAppStore((s) => s.pdfs);
  const totalTables = useAppStore((s) => s.totalTables);
  const activeTab = useAppStore((s) => s.activeTab);
  const addPdfs = useAppStore((s) => s.addPdfs);
  const removePdf = useAppStore((s) => s.removePdf);
  const setPdfs = useAppStore((s) => s.setPdfs);
  const setSession = useAppStore((s) => s.setSession);
  const setUploading = useAppStore((s) => s.setUploading);
  const restoreFromStorage = useAppStore((s) => s.restoreFromStorage);
  const reset = useAppStore((s) => s.reset);

  const did404Ref = useRef(false);

  const [tableGroupSuggestions, setTableGroupSuggestions] = useState<TableGroupSuggestion[]>([]);

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
        did404Ref.current = false;
        setSession(data.session_id, data.name || name);
      }
    } catch (e) {
      alert('세션 생성 실패');
    }
  }, [setSession]);

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
    const state = useAppStore.getState();
    const filteredResults = state.results.filter((r) => r.document_name !== name);
    const filteredSmart = state.smartResult && state.smartResult.result.document_name !== name
      ? state.smartResult : null;
    const filteredQA = state.qaMessages.filter((m) => {
      const sources = (m as { sources?: { document_name?: string }[] }).sources;
      if (!sources) return true;
      return !sources.some((s) => s.document_name === name);
    });
    useAppStore.setState({
      results: filteredResults,
      smartResult: filteredSmart,
      qaMessages: filteredQA,
    });
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
      if (result.table_group_suggestions && result.table_group_suggestions.length > 0) {
        setTableGroupSuggestions(result.table_group_suggestions);
      }
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
        return <UnifiedSearchView />;

      case 'translation':
        return <TranslationView />;

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

        <main className={`flex-1 overflow-hidden ${activeTab === 'document' ? '' : 'overflow-y-auto p-6'}`}>
          {renderContent()}
        </main>
      </div>

      {tableGroupSuggestions.length > 0 && (
        <TableGroupSuggestionPopup
          suggestions={tableGroupSuggestions}
          onComplete={() => setTableGroupSuggestions([])}
        />
      )}
    </div>
  );
}
