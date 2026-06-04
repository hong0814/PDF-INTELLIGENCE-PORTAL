import { useState, type FormEvent } from 'react';
import type { LoginPreAuthResponse } from '../types';

interface OtpOverlayProps {
  preAuth: LoginPreAuthResponse;
  isSubmitting: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (otpCode: string) => Promise<void>;
}

export default function OtpOverlay({
  preAuth,
  isSubmitting,
  error,
  onCancel,
  onSubmit,
}: OtpOverlayProps) {
  const [otpCode, setOtpCode] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!otpCode.trim()) return;
    await onSubmit(otpCode.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-6">
      <form
        onSubmit={submit}
        className="w-full max-w-[360px] rounded-2xl border border-[#303741] bg-[#212831] p-6 shadow-[0_18px_60px_rgba(0,0,0,0.45)]"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-[#f0f6fc]">OTP 인증</h2>
            <p className="mt-1 text-sm leading-5 text-[#9da7b3]">
              <span className="text-[#f0f6fc]">{preAuth.user.name || preAuth.user.username}</span> 계정 확인을 위해 OTP 코드를 입력하세요.
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="rounded-md px-2 py-1 text-lg leading-none text-[#9da7b3] transition-colors hover:bg-[#303741] hover:text-[#f0f6fc] disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="OTP 닫기"
          >
            x
          </button>
        </div>

        <label className="block space-y-1.5">
          <span className="block text-[0.78rem] font-medium tracking-[0.02em] text-[#9da7b3]">OTP Code</span>
          <input
            autoFocus
            value={otpCode}
            onChange={(event) => setOtpCode(event.target.value)}
            className="w-full rounded-[10px] border border-[#303741] bg-[#161b22] px-[14px] py-[10px] text-sm text-[#f0f6fc] outline-none transition-[border-color,box-shadow] placeholder:text-[#7d8590] focus:border-[#2f81f7] focus:ring-[3px] focus:ring-[rgba(47,129,247,0.2)] disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isSubmitting}
            inputMode="numeric"
            placeholder="Enter OTP code"
          />
        </label>

        {error && (
          <div className="mt-3 min-h-[1.1em] text-sm text-[#ff7b72]">
            {error}
          </div>
        )}

        <div className="mt-5 flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="flex-1 rounded-lg border border-[#303741] px-4 py-[10px] text-sm font-medium text-[#9da7b3] transition-colors hover:bg-[#303741] hover:text-[#f0f6fc] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSubmitting || !otpCode.trim()}
            className="flex-1 rounded-lg bg-[#2f81f7] px-4 py-[10px] text-sm font-semibold text-white transition-colors hover:bg-[#1f6feb] disabled:cursor-not-allowed disabled:bg-[#4b5563]"
          >
            {isSubmitting ? 'Verifying...' : 'Verify'}
          </button>
        </div>
      </form>
    </div>
  );
}
