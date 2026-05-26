import { useState, useRef, useCallback, useEffect } from 'react';
import type { PdfInfo, SessionInfo } from '../types';
import { useAppStore } from '../store/useAppStore';
import * as api from '../api/client';
import { BASE } from '../api/client';

interface SidebarProps {
  sessionId: string;
  pdfs: PdfInfo[];
  totalTables: number;
  onUploadComplete: (sessionId: string, pdfs: Record<string, { table_count: number; page_count: number }>, totalTables: number, totalPages: number) => void;
  onDeletePdf: (name: string) => void;
  onReset: () => void;
}

export default function Sidebar({ sessionId, pdfs, totalTables, onUploadComplete, onDeletePdf, onReset }: SidebarProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadTime, setUploadTime] = useState<number | null>(null);
  const [showTips, setShowTips] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [currentSession, setCurrentSession] = useState<SessionInfo | null>(null);
  const isUploading = useAppStore((s) => s.isUploading);
  const setStoreUploading = useAppStore((s) => s.setUploading);
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const setSession = useAppStore((s) => s.setSession);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshCurrentSession = useCallback(() => {
    if (!sessionId) return;
    api.getSession(sessionId).then((info: SessionInfo) => {
      setCurrentSession(info);
    }).catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    api.getSessions().then((data: import('../types').SessionsResponse) => {
      setSessions(data.sessions ?? []);
    }).catch(() => {});
    refreshCurrentSession();
  }, [sessionId, refreshCurrentSession]);

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const pdfFiles = Array.from(files).filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
    if (pdfFiles.length === 0) return;

    const startTime = performance.now();
    setUploadProgress(0);
    setUploadTime(null);
    const progressInterval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev === null) return null;
        return prev >= 90 ? 90 : prev + Math.random() * 15;
      });
    }, 300);

    try {
      setStoreUploading(true);
      const result = await api.uploadPdfs(pdfFiles, sessionId);
      clearInterval(progressInterval);
      const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
      setUploadTime(Number(elapsed));
      setUploadProgress(100);
      setTimeout(() => setUploadProgress(null), 800);
      onUploadComplete(result.session_id, result.pdfs, result.total_tables, result.total_pages ?? 0);
      refreshCurrentSession();
      api.getSessions().then((data: import('../types').SessionsResponse) => {
        setSessions(data.sessions ?? []);
      }).catch(() => {});
    } catch (err) {
      clearInterval(progressInterval);
      setUploadProgress(null);
      setUploadTime(null);
      alert(err instanceof Error ? err.message : '업로드 실패');
    } finally {
      setStoreUploading(false);
    }
  }, [onUploadComplete, sessionId, setStoreUploading]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  }, [handleFiles]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
      e.target.value = '';
    }
  }, [handleFiles]);

  const handleDelete = useCallback(async (name: string) => {
    if (!confirm(`"${name}"을(를) 삭제하시겠습니까?`)) return;
    try {
      await api.deletePdf(name, sessionId);
      onDeletePdf(name);
    } catch (err) {
      alert(err instanceof Error ? err.message : '삭제 실패');
    }
  }, [sessionId, onDeletePdf]);

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

  return (
    <aside className={`${collapsed ? 'w-[48px] min-w-[48px]' : 'w-[280px] min-w-[280px]'} bg-sidebar text-white flex flex-col h-full overflow-y-auto transition-all duration-200`}>
      <div className={`pt-5 pb-4 border-b border-white/10 ${collapsed ? 'px-2' : 'px-4'}`}>
        <div className="flex items-center gap-2.5 mb-1.5">
          {!collapsed && (
            <svg className="w-6 h-6 text-primary flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          )}
          {!collapsed && <span className="font-bold text-sm">PDF Intelligence Portal</span>}
          <button
            onClick={toggleSidebar}
            className={`${collapsed ? 'mx-auto' : 'ml-auto'} p-1.5 rounded hover:bg-white/10 transition-colors flex-shrink-0`}
            title={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              {collapsed
                ? <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                : <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" />
              }
            </svg>
          </button>
        </div>
        {!collapsed && <p className="text-[11px] text-white/40">AI 기반 문서 분석 & 질의응답</p>}
      </div>

      {collapsed ? (
        <div className="flex flex-col items-center py-3 gap-2">
          {pdfs.map((pdf) => (
            <div key={pdf.name} className="w-8 h-8 rounded bg-white/10 flex items-center justify-center text-[10px] font-bold" title={pdf.name}>
              {pdf.name.charAt(0).toUpperCase()}
            </div>
          ))}
        </div>
      ) : (
        <>
        <div className="p-4 pt-5">
          <h2 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">PDF 관리</h2>

        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            border-2 border-dashed rounded-lg p-5 text-center cursor-pointer transition-all duration-200
            ${isDragging
              ? 'border-accent bg-accent/10 scale-[1.02]'
              : 'border-white/20 hover:border-white/40 hover:bg-white/5'
            }
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            multiple
            onChange={handleFileInput}
            className="hidden"
          />
          <svg className="w-8 h-8 mx-auto text-white/30 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0L8 8m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
          </svg>
          <p className="text-sm text-white/50">
            {isDragging ? '여기에 놓으세요' : 'PDF 파일을 드래그하거나 클릭'}
          </p>
          <p className="text-xs text-white/30 mt-1">.pdf 파일만 지원</p>
        </div>

        {isUploading && (
          <div className="mt-3">
            <div className="flex items-center gap-2 text-xs text-accent mb-2">
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              업로드 및 분석 중...
            </div>
            <div className="w-full bg-white/10 rounded-full h-1.5 overflow-hidden">
              <div className="h-full bg-accent rounded-full animate-pulse" style={{ width: '100%' }} />
            </div>
          </div>
        )}

        {uploadProgress !== null && (
          <div className="mt-3">
            <div className="flex justify-between text-xs text-white/50 mb-1">
              <span>{uploadProgress < 100 ? '업로드 중...' : '업로드 완료!'}</span>
              <span>{uploadProgress < 100 ? `${Math.round(uploadProgress)}%` : '✓'}</span>
            </div>
            <div className="w-full bg-white/10 rounded-full h-1.5 overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-300 ease-out"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {uploadProgress === null && uploadTime !== null && (
          <div className="mt-2 text-xs text-success/80 text-center fade-in">
            업로드 완료 · {uploadTime}초 소요
          </div>
        )}

        {pdfs.length > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-white/40">업로드된 문서</span>
              <span className="text-xs bg-accent/20 text-accent px-2 py-0.5 rounded-full font-medium">
                표 {totalTables}개
              </span>
            </div>
            <ul className="space-y-1">
              {pdfs.map((pdf) => (
                <li
                  key={pdf.name}
                  className="flex items-center justify-between group bg-white/5 hover:bg-white/10 rounded-md px-3 py-2 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm truncate">{pdf.name}</p>
                    <p className="text-xs text-white/40">표 {pdf.table_count}개</p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(pdf.name); }}
                    className="opacity-0 group-hover:opacity-100 ml-2 text-white/30 hover:text-danger transition-all p-1 rounded"
                    title="삭제"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="border-t border-white/10 overflow-y-auto flex-1">
        <div className="px-4 py-3">
          <h2 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-2">세션 관리</h2>

          <div className="mb-3 px-3 py-2.5 bg-white/5 rounded-md">
            <p className="text-[10px] uppercase tracking-wider text-white/30 mb-1">현재 세션</p>
            <p className="text-sm text-white/80 truncate font-medium">
              {currentSession?.name || '세션'}
            </p>
            {currentSession?.created_at && (
              <p className="text-[10px] text-white/30 mt-0.5">
                {new Date(currentSession.created_at).toLocaleString('ko-KR')}
              </p>
            )}
            {currentSession?.pdf_names && currentSession.pdf_names.length > 0 && (
              <p className="text-[10px] text-white/25 mt-0.5 truncate">
                {currentSession.pdf_names.join(', ')}
              </p>
            )}
          </div>

          {sessions.length > 0 && (
            <ul className="space-y-1 mb-3">
              {sessions.map((session) => (
                <li key={session.session_id} className="group relative">
                  <button
                    className="w-full text-left bg-white/5 hover:bg-white/10 rounded-md px-3 py-2 transition-colors pr-8"
                    onClick={() => { window.location.href = `/?session=${session.session_id}`; }}
                  >
                    <p className="text-sm truncate text-white/90">{session.name}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] bg-primary/20 text-primary/80 px-1.5 py-0.5 rounded font-medium">
                        검색 {session.search_count}회
                      </span>
                      <span className="text-[10px] bg-success/20 text-success/80 px-1.5 py-0.5 rounded font-medium">
                        텍스트검색 {session.qa_count}회
                      </span>
                    </div>
                    <p className="text-xs text-white/30 mt-1">
                      {new Date(session.created_at).toLocaleString('ko-KR')}
                    </p>
                    {session.pdf_names && session.pdf_names.length > 0 && (
                      <p className="text-[10px] text-white/25 mt-0.5 truncate">
                        {session.pdf_names.join(', ')}
                      </p>
                    )}
                  </button>
                  <button
                    className="absolute top-2 right-2 p-1 rounded hover:bg-red-500/30 text-white/0 group-hover:text-white/50 hover:!text-red-400 transition-colors"
                    title="세션 삭제"
                    onClick={async (e) => {
                      e.stopPropagation();
                      if (!confirm(`"${session.name}" 세션을 삭제할까요?`)) return;
                      try {
                        await fetch(`${BASE}/sessions/${session.session_id}`, { method: 'DELETE' });
                        if (session.session_id === sessionId) {
                          localStorage.removeItem('pdftablesearch_session_id');
                          setSession('', '');
                        }
                        const data = await api.getSessions();
                        setSessions(data.sessions ?? []);
                      } catch { alert('삭제 실패'); }
                    }}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <button
            onClick={handleCreateSession}
            className="w-full py-2 px-3 text-sm text-white/40 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center justify-center gap-2 border border-dashed border-white/20 hover:border-white/40"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            새 세션 만들기
          </button>
        </div>
      </div>

      <div className="p-4 border-t border-white/10 space-y-2">
        <button
          onClick={onReset}
          className="w-full py-2 px-3 text-sm text-white/50 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center justify-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          세션 초기화
        </button>

        <button
          onClick={() => setShowTips(!showTips)}
          className="w-full py-2 px-3 text-sm text-white/50 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center justify-between"
        >
          <span className="flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            사용 안내
          </span>
          <svg className={`w-4 h-4 transition-transform ${showTips ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showTips && (
          <div className="text-xs text-white/40 leading-relaxed space-y-2 bg-white/5 rounded-lg p-3 fade-in">
            <p>1. PDF 파일을 업로드하세요</p>
            <p>2. 검색어로 표를 찾으세요</p>
            <p>3. Smart Search로 AI가 최적의 표를 추천합니다</p>
            <p>4. 각 표에 대해 질문할 수 있습니다</p>
          </div>
        )}
      </div>
      </>
      )}

      <div className="p-3 border-t border-white/10 text-center">
        <p className="text-[10px] text-white/30">{collapsed ? '' : 'PDF Intelligence Portal v0.1.0'}</p>
      </div>
    </aside>
  );
}
