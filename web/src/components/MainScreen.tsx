import { useState, useRef, useCallback } from 'react';
import { useAppStore } from '../store/useAppStore';

interface MainScreenProps {
  onUpload: (files: FileList) => Promise<void>;
  hasDocuments?: boolean;
}

export default function MainScreen({ onUpload, hasDocuments }: MainScreenProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const setActiveTab = useAppStore((s) => s.setActiveTab);

  const triggerUpload = useCallback(async (files: FileList) => {
    setUploading(true);
    await onUpload(files);
    setUploading(false);
  }, [onUpload]);

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
      triggerUpload(e.dataTransfer.files);
    }
  }, [triggerUpload]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      triggerUpload(e.target.files);
      e.target.value = '';
    }
  }, [triggerUpload]);

  if (hasDocuments) {
    return (
      <div className="max-w-4xl mx-auto fade-in">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-text-primary mb-2 tracking-tight">
            PDF Intelligence Portal
          </h1>
          <p className="text-sm text-text-secondary">
            원하는 기능을 선택하세요
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <NavLink
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            }
            title="문서 보기"
            description="업로드된 PDF 문서를 확인하고 페이지별로 탐색합니다"
            onClick={() => setActiveTab('document')}
          />
          <NavLink
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
            }
            title="문서 검색"
            description="표와 텍스트를 통합 검색. AI가 관련 문서를 찾아 답변합니다."
            onClick={() => setActiveTab('search')}
          />
        </div>

        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            mt-8 w-full border-2 border-dashed rounded-xl p-6 text-center cursor-pointer
            transition-all duration-200 ease-out
            ${uploading
              ? 'border-primary bg-primary/5 pointer-events-none'
              : isDragging
              ? 'border-primary bg-primary-light/60 scale-[1.01]'
              : 'border-border hover:border-primary/50 hover:bg-surface-elevated'
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
          {uploading ? (
            <div className="flex items-center justify-center gap-2 text-sm text-primary">
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              PDF 업로드 및 분석 중...
            </div>
          ) : (
            <p className="text-sm text-text-muted">
              {isDragging ? '여기에 놓으세요' : '추가 PDF 파일을 드래그하거나 클릭하여 업로드'}
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-full px-6 py-10 fade-in">
      <div className="text-center mb-10">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-primary rounded-2xl shadow-lg shadow-primary/25 mb-6">
          <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
        </div>

        <h1 className="text-3xl font-bold text-text-primary mb-2 tracking-tight">
          PDF Intelligence Portal
        </h1>
        <p className="text-lg text-primary font-medium mb-4">
          AI 기반 문서 분석 &amp; 질의응답
        </p>
        <p className="text-sm text-text-secondary max-w-lg mx-auto leading-relaxed">
          PDF 문서를 업로드하면 AI가 자동으로 표를 추출하고 분석합니다.
          자연어로 표를 검색하고, 각 표에 대해 질문하여 인사이트를 얻을 수 있습니다.
        </p>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`
          w-full max-w-2xl min-h-[400px] border-2 border-dashed rounded-2xl
          flex flex-col items-center justify-center cursor-pointer
          transition-all duration-200 ease-out
          ${isDragging
            ? 'border-primary bg-primary-light/60 scale-[1.01] shadow-lg shadow-primary/10'
            : 'border-border hover:border-primary/50 hover:bg-surface-elevated hover:shadow-md'
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

        {uploading ? (
          <>
            <div className="mb-5">
              <svg className="w-14 h-14 text-primary animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.338-2.32 3.75 3.75 0 013.962 4.108 3 3 0 01-.389 5.987H6.75z" />
              </svg>
            </div>
            <p className="text-base font-medium text-primary mb-1">PDF 업로드 및 분석 중...</p>
            <p className="text-sm text-text-muted">잠시만 기다려주세요</p>
          </>
        ) : (
          <>
            <div className={`mb-5 transition-transform duration-200 ${isDragging ? 'scale-110 -translate-y-1' : ''}`}>
              <svg className="w-14 h-14 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.338-2.32 3.75 3.75 0 013.962 4.108 3 3 0 01-.389 5.987H6.75z" />
              </svg>
            </div>
            <p className="text-base font-medium text-text-primary mb-1">
              {isDragging ? '여기에 놓으세요' : 'PDF 파일을 드래그하여 업로드'}
            </p>
            <p className="text-sm text-text-muted">
              {isDragging ? '파일을 놓으면 업로드가 시작됩니다' : '또는 클릭하여 파일 선택'}
            </p>
          </>
        )}

        <div className="mt-8 px-4 py-2 bg-surface rounded-lg">
          <p className="text-xs text-text-muted">지원 형식: .pdf</p>
        </div>
      </div>

      <div className="w-full max-w-2xl grid grid-cols-2 gap-4 mt-10">
        <FeatureCard
          icon={
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          }
          title="문서 보기"
          description="업로드된 PDF 문서를 확인하고 페이지별로 탐색합니다"
        />
        <FeatureCard
          icon={
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
          }
          title="문서 검색"
          description="표와 텍스트를 통합 검색. AI가 관련 문서를 찾아 답변합니다."
        />
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description }: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="bg-surface-elevated border border-border rounded-xl p-5 transition-all duration-200 hover:shadow-lg hover:shadow-primary/5 hover:-translate-y-0.5 hover:border-primary/20">
      <div className="w-10 h-10 bg-primary-light rounded-lg flex items-center justify-center text-primary mb-3">
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-text-primary mb-1.5">{title}</h3>
      <p className="text-xs text-text-secondary leading-relaxed">{description}</p>
    </div>
  );
}

function NavLink({ icon, title, description, onClick }: {
  icon: React.ReactNode;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="bg-surface-elevated border border-border rounded-xl p-5 text-left transition-all duration-200 hover:shadow-lg hover:shadow-primary/5 hover:-translate-y-0.5 hover:border-primary/30 group w-full"
    >
      <div className="w-10 h-10 bg-primary-light rounded-lg flex items-center justify-center text-primary mb-3 group-hover:bg-primary group-hover:text-white transition-colors">
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-text-primary mb-1.5">{title}</h3>
      <p className="text-xs text-text-secondary leading-relaxed">{description}</p>
      <span className="inline-flex items-center gap-1 mt-3 text-xs text-primary font-medium opacity-0 group-hover:opacity-100 transition-opacity">
        이동
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </span>
    </button>
  );
}
