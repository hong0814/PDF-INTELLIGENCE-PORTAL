import { useState, useCallback } from 'react';
import { useAppStore } from '../store/useAppStore';
import { BASE, apiFetch } from '../api/client';
import DocumentViewer from './DocumentViewer';

type SubTab = 'images' | 'fund';

interface ImageItem {
  index: number;
  alt: string;
  src: string;
  page_image_src: string;
  prev_text: string;
  next_text: string;
  page: number;
  in_table: boolean;
  table_context: { cell_text: string; caption: string } | null;
}

export default function CreditReviewView() {
  const pdfs = useAppStore((s) => s.pdfs);
  const sessionId = useAppStore((s) => s.sessionId);
  const [subTab, setSubTab] = useState<SubTab>('images');

  const [selectedPdf, setSelectedPdf] = useState<string>('');
  const [images, setImages] = useState<ImageItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLoadImages = useCallback(async () => {
    if (!selectedPdf) return;
    setIsLoading(true);
    setError(null);
    setImages([]);

    try {
      const res = await apiFetch(
        `${BASE}/documents/images?name=${encodeURIComponent(selectedPdf)}`,
        { headers: { 'X-Session-ID': sessionId } },
      );
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = await res.json();
      setImages(data.images || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : '이미지 로드 실패');
    } finally {
      setIsLoading(false);
    }
  }, [selectedPdf, sessionId]);

  if (pdfs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-full px-6 fade-in">
        <div className="w-16 h-16 bg-surface-elevated border border-border rounded-2xl flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.41a2.25 2.25 0 013.182 0l2.909 2.91m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-text-primary mb-1">기업금융심사</h2>
        <p className="text-sm text-text-muted">PDF를 업로드하면 이미지를 분석할 수 있습니다.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Sub-tab bar */}
      <div className="flex items-center gap-1 px-4 py-2 border-b bg-surface-elevated">
        <button
          onClick={() => setSubTab('images')}
          className={`px-4 py-1.5 text-sm rounded-lg transition-colors ${
            subTab === 'images' ? 'bg-primary/10 text-primary font-medium' : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          이미지 검색
        </button>
        <button
          onClick={() => setSubTab('fund')}
          className={`px-4 py-1.5 text-sm rounded-lg transition-colors ${
            subTab === 'fund' ? 'bg-primary/10 text-primary font-medium' : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          기금 문서 보기
        </button>
      </div>

      {/* Sub-tab content */}
      {subTab === 'images' ? (
        <ImageView
          pdfs={pdfs}
          selectedPdf={selectedPdf}
          setSelectedPdf={setSelectedPdf}
          images={images}
          setImages={setImages}
          isLoading={isLoading}
          setIsLoading={setIsLoading}
          error={error}
          setError={setError}
          handleLoadImages={handleLoadImages}
        />
      ) : (
        <DocumentViewer tableFilter="inner" />
      )}
    </div>
  );
}

function ImageView({ pdfs, selectedPdf, setSelectedPdf, images, isLoading, error, handleLoadImages }: {
  pdfs: { name: string }[];
  selectedPdf: string;
  setSelectedPdf: (v: string) => void;
  images: ImageItem[];
  setImages: (v: ImageItem[]) => void;
  isLoading: boolean;
  setIsLoading: (v: boolean) => void;
  error: string | null;
  setError: (v: string | null) => void;
  handleLoadImages: () => void;
}) {
  return (
    <div className="flex flex-col h-full max-w-full mx-auto">
      <div className="px-5 py-3 border-b bg-surface-elevated flex items-center justify-between">
        <span className="text-sm font-semibold">기업금융심사 — 문서 이미지 분석</span>
        {images.length > 0 && (
          <span className="text-xs text-text-muted">{images.length}개 이미지</span>
        )}
      </div>

      <div className="px-6 py-3 border-b bg-white flex items-center gap-4">
        <select
          value={selectedPdf}
          onChange={(e) => setSelectedPdf(e.target.value)}
          className="text-sm border border-border rounded-lg px-3 py-2"
          disabled={isLoading}
        >
          <option value="">문서 선택...</option>
          {pdfs.map((p) => (
            <option key={p.name} value={p.name}>{p.name}</option>
          ))}
        </select>
        <button
          onClick={handleLoadImages}
          disabled={!selectedPdf || isLoading}
          className="text-sm px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover disabled:opacity-50 transition-colors"
        >
          {isLoading ? '분석 중...' : '이미지 추출'}
        </button>
      </div>

      {isLoading && (
        <div className="px-6 py-8 flex items-center justify-center gap-3 text-sm text-text-muted">
          <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span>PDF에서 이미지를 추출하고 있습니다...</span>
        </div>
      )}

      {error && (
        <div className="px-6 py-4 border-t bg-danger/5">
          <p className="text-sm text-error">{error}</p>
        </div>
      )}

      {!isLoading && images.length > 0 && (
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {images.map((img) => (
              <ImageCard key={img.index} image={img} />
            ))}
          </div>
        </div>
      )}

      {!isLoading && images.length === 0 && selectedPdf && !error && (
        <div className="flex-1 flex flex-col items-center justify-center text-text-muted text-sm">
          <svg className="w-12 h-12 mb-3 text-border" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.41a2.25 2.25 0 013.182 0l2.909 2.91m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
          </svg>
          <p>문서를 선택하고 이미지 추출 버튼을 클릭하세요</p>
        </div>
      )}
    </div>
  );
}

function ImageCard({ image }: { image: ImageItem }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      const resp = await fetch(image.src);
      const blob = await resp.blob();
      await navigator.clipboard.write([
        new ClipboardItem({ [blob.type]: blob }),
      ]);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      alert('클립보드 복사에 실패했습니다.');
    }
  };

  const handleDownload = () => {
    const a = document.createElement('a');
    a.href = image.src;
    a.download = `${image.alt || `image_${image.index}`}.png`;
    a.click();
  };

  return (
    <div className="border border-border rounded-xl overflow-hidden bg-white shadow-sm hover:shadow-md transition-shadow">
      <div className="relative bg-gray-50 border-b border-border">
        <img
          src={image.src}
          alt={image.alt}
          className="max-w-full h-auto mx-auto block bg-white"
          loading="lazy"
        />
        <div className="absolute top-2 right-2 flex gap-1.5">
          <span className="text-[10px] bg-white/90 text-text-muted px-2 py-0.5 rounded-full border border-border">
            {image.page}페이지
          </span>
          {image.in_table && (
            <span className="text-[10px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-200">
              표 내부
            </span>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 px-4 pt-3">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border bg-white hover:bg-gray-50 transition-colors text-text-secondary"
        >
          {copied ? (
            <>
              <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              복사됨
            </>
          ) : (
            <>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
              </svg>
              복사
            </>
          )}
        </button>
        <button
          onClick={handleDownload}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border bg-white hover:bg-gray-50 transition-colors text-text-secondary"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
          다운로드
        </button>
      </div>

      {/* Context info */}
      <div className="p-4 pt-2 space-y-2">
        <div className="flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.41a2.25 2.25 0 013.182 0l2.909 2.91m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
          </svg>
          <span className="text-xs font-semibold text-text-primary">{image.alt}</span>
        </div>

        {image.table_context && (image.table_context.caption || image.table_context.cell_text) && (
          <div className="text-xs text-blue-600 bg-blue-50 px-2 py-1.5 rounded-lg">
            <span className="font-medium">표 컨텍스트: </span>
            {image.table_context.caption || image.table_context.cell_text}
          </div>
        )}

        {image.prev_text && (
          <div className="text-xs text-text-muted leading-relaxed bg-gray-50 px-3 py-2 rounded-lg">
            <span className="font-medium text-text-secondary">이전 텍스트: </span>
            ...{image.prev_text}
          </div>
        )}

        {image.next_text && (
          <div className="text-xs text-text-muted leading-relaxed bg-gray-50 px-3 py-2 rounded-lg">
            <span className="font-medium text-text-secondary">이후 텍스트: </span>
            {image.next_text}...
          </div>
        )}

        {!image.prev_text && !image.next_text && (
          <div className="text-xs text-text-muted italic">주변 텍스트 없음</div>
        )}
      </div>
    </div>
  );
}
