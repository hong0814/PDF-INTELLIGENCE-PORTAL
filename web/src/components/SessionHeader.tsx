import { useRef, useCallback, useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import * as api from '../api/client';

interface SessionHeaderProps {
  onLogout: () => Promise<void>;
}

export default function SessionHeader({ onLogout }: SessionHeaderProps) {
  const user = useAppStore((s) => s.user);
  const sessionName = useAppStore((s) => s.sessionName);
  const pdfs = useAppStore((s) => s.pdfs);
  const totalTables = useAppStore((s) => s.totalTables);
  const sessionId = useAppStore((s) => s.sessionId);
  const addPdfs = useAppStore((s) => s.addPdfs);
  const setActiveTab = useAppStore((s) => s.setActiveTab);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleUpload = useCallback(async (files: FileList | File[]) => {
    const pdfFiles = Array.from(files).filter(
      (f) => f.type === 'application/pdf' || f.name.endsWith('.pdf')
    );
    if (pdfFiles.length === 0) return;

    try {
      const result = await api.uploadPdfs(pdfFiles, sessionId);
      const pdfList = Object.entries(result.pdfs).map(([name, info]) => ({
        name,
        table_count: info.table_count,
      }));
      addPdfs(pdfList, result.total_tables, result.total_pages ?? 0);
    } catch (err) {
      alert(err instanceof Error ? err.message : '업로드 실패');
    }
  }, [sessionId, addPdfs]);

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
      handleUpload(e.dataTransfer.files);
    }
  }, [handleUpload]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleUpload(e.target.files);
      e.target.value = '';
    }
  }, [handleUpload]);

  return (
    <header className="flex items-center gap-4 px-5 py-3 bg-surface-elevated border-b border-border">
      <div className="flex items-center gap-2 min-w-0">
        <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center shrink-0">
          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
        </div>
        <span className="text-sm font-semibold text-text-primary truncate">{sessionName}</span>
      </div>

      <div className="flex items-center gap-2 flex-1 overflow-x-auto min-w-0 px-2">
        {pdfs.map((pdf) => (
          <button
            key={pdf.name}
            onClick={() => setActiveTab('document')}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface border border-border rounded-lg text-xs text-text-secondary hover:bg-primary-light hover:text-primary hover:border-primary/30 transition-colors shrink-0"
          >
            <svg className="w-3.5 h-3.5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="truncate max-w-[120px]">{pdf.name}</span>
            <span className="bg-primary/10 text-primary px-1.5 py-0.5 rounded text-[10px] font-medium">
              {pdf.table_count}표
            </span>
          </button>
        ))}

        {totalTables > 0 && (
          <span className="text-xs text-text-muted shrink-0">
            총 {totalTables}개 테이블
          </span>
        )}
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 border border-dashed rounded-lg text-xs cursor-pointer transition-all shrink-0
          ${isDragging
            ? 'border-primary bg-primary-light/60 text-primary'
            : 'border-border text-text-muted hover:border-primary/40 hover:text-primary'
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
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        PDF 추가
      </div>

      <div className="flex items-center gap-2 shrink-0 pl-2 border-l border-border">
        <div className="text-right">
          <p className="text-xs font-medium text-text-primary">{user?.name || user?.username}</p>
          <p className="text-[11px] text-text-muted">{user?.department || user?.email || 'LDAP 사용자'}</p>
        </div>
        <button
          className="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary hover:text-text-primary hover:bg-surface transition-colors"
          onClick={() => { void onLogout(); }}
        >
          로그아웃
        </button>
      </div>
    </header>
  );
}
