import { useState } from 'react';

interface AgreementOverlayProps {
  onCancel: () => void;
  onConfirm: () => void;
}

export default function AgreementOverlay({ onCancel, onConfirm }: AgreementOverlayProps) {
  const [accepted, setAccepted] = useState(false);

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/45 px-6">
      <div className="w-full max-w-[560px] rounded-lg border border-border bg-surface-elevated shadow-xl">
        <div className="border-b border-border px-6 py-4">
          <h2 className="text-lg font-semibold text-text-primary">서비스 이용 안내 및 동의</h2>
          <p className="mt-1 text-sm text-text-secondary">
            PDF Intelligence Portal 사용 전 아래 내용을 확인해주세요.
          </p>
        </div>

        <div className="max-h-[58vh] overflow-y-auto px-6 py-5 text-sm leading-6 text-text-secondary">
          <p className="mb-4">
            본 서비스는 업로드한 PDF 문서에서 필요한 내용을 빠르게 찾고, 표 데이터를 확인하거나 CSV로
            다운로드하며, 문서 내용 번역을 보조하기 위한 내부 업무 도구입니다.
          </p>

          <section className="mb-4">
            <h3 className="mb-2 font-semibold text-text-primary">처리되는 데이터</h3>
            <ul className="list-disc space-y-1 pl-5">
              <li>PDF 원본 파일, 문서 텍스트, 표 구조, 검색 및 번역 요청 내용이 처리될 수 있습니다.</li>
              <li>개인정보 또는 민감정보가 포함된 경우 탐지 가능한 항목은 마스킹 처리됩니다.</li>
              <li>마스킹은 자동 처리 기준에 따라 수행되므로, 업로드 전 필요한 최소 범위의 문서만 사용해주세요.</li>
            </ul>
          </section>

          <section className="mb-4">
            <h3 className="mb-2 font-semibold text-text-primary">보관 및 삭제</h3>
            <ul className="list-disc space-y-1 pl-5">
              <li>업로드된 PDF 원본 파일은 업로드 후 7일이 지나면 삭제됩니다.</li>
              <li>업무상 보관이 필요한 결과물은 삭제 전 CSV 또는 필요한 형식으로 별도 저장해주세요.</li>
            </ul>
          </section>

          <section>
            <h3 className="mb-2 font-semibold text-text-primary">사용자 확인 사항</h3>
            <ul className="list-disc space-y-1 pl-5">
              <li>본인은 업무 목적에 필요한 문서만 업로드합니다.</li>
              <li>제3자에게 공개하면 안 되는 정보는 사내 보안 기준에 맞게 처리합니다.</li>
              <li>자동 추출, 번역, 표 인식 결과는 업무 반영 전 직접 검토합니다.</li>
            </ul>
          </section>
        </div>

        <div className="border-t border-border px-6 py-4">
          <label className="mb-4 flex cursor-pointer items-start gap-3 text-sm text-text-secondary">
            <input
              checked={accepted}
              onChange={(event) => setAccepted(event.target.checked)}
              type="checkbox"
              className="mt-1 h-4 w-4 rounded border-border text-primary focus:ring-primary/30"
            />
            <span>위 안내 사항을 확인했으며, 서비스 이용 조건에 동의합니다.</span>
          </label>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onCancel}
              className="h-10 rounded-md border border-border px-4 text-sm font-medium text-text-secondary hover:bg-surface transition-colors"
            >
              취소
            </button>
            <button
              type="button"
              disabled={!accepted}
              onClick={onConfirm}
              className="h-10 rounded-md bg-primary px-5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              확인
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
