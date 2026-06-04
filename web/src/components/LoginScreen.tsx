import { useState, type FormEvent } from 'react';
import * as api from '../api/client';
import type { AuthStatus, PreAuthStatus } from '../types';

interface LoginScreenProps {
  onLogin: (status: AuthStatus) => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [preAuth, setPreAuth] = useState<PreAuthStatus | null>(null);
  const [error, setError] = useState('');
  const [otpError, setOtpError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isOtpSubmitting, setIsOtpSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) return;
    setError('');
    setIsSubmitting(true);
    try {
      const nextPreAuth = await api.loginWithLdap(username.trim(), password);
      setPreAuth(nextPreAuth);
      setOtpCode('');
      setOtpError('');
    } catch {
      setError('아이디 또는 비밀번호를 확인하세요.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitOtp = async (event: FormEvent) => {
    event.preventDefault();
    if (!preAuth || !otpCode.trim()) return;
    setOtpError('');
    setIsOtpSubmitting(true);
    try {
      const status = await api.verifyOtp(preAuth.pre_auth_token, otpCode.trim());
      setPreAuth(null);
      setOtpCode('');
      onLogin(status);
    } catch {
      setOtpError('OTP 코드를 확인하세요. 시간이 만료된 경우 다시 로그인하세요.');
    } finally {
      setIsOtpSubmitting(false);
    }
  };

  const closeOtp = () => {
    setPreAuth(null);
    setOtpCode('');
    setOtpError('');
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#161b22] px-6 py-8">
      <div className="w-full max-w-[400px] rounded-2xl border border-[#303741] bg-[#212831] px-8 py-9 shadow-[0_4px_24px_rgba(0,0,0,0.35)]">
        <div className="flex flex-col items-center gap-3">
          <img
            alt="PDF Intelligence Portal"
            className="h-12 w-auto object-contain"
            src="/logo.svg"
          />
          <div className="space-y-1 text-center">
            <h1 className="text-[1.2rem] font-semibold text-[#f0f6fc]">PDF Intelligence Portal</h1>
          </div>
        </div>

        <div className="my-5 h-px bg-[#303741]" />

        <form onSubmit={submit} className="space-y-4">
          <label className="block space-y-1.5">
            <span className="block text-[0.78rem] font-medium tracking-[0.02em] text-[#9da7b3]">ID</span>
            <input
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full rounded-[10px] border border-[#303741] bg-[#212831] px-[14px] py-[10px] text-sm text-[#f0f6fc] outline-none transition-[border-color,box-shadow] placeholder:text-[#7d8590] focus:border-[#2f81f7] focus:ring-[3px] focus:ring-[rgba(47,129,247,0.2)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting || isOtpSubmitting}
              autoComplete="username"
              placeholder="Enter your ID"
              spellCheck={false}
            />
          </label>
          <label className="block space-y-1.5">
            <span className="block text-[0.78rem] font-medium tracking-[0.02em] text-[#9da7b3]">Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-[10px] border border-[#303741] bg-[#212831] px-[14px] py-[10px] text-sm text-[#f0f6fc] outline-none transition-[border-color,box-shadow] placeholder:text-[#7d8590] focus:border-[#2f81f7] focus:ring-[3px] focus:ring-[rgba(47,129,247,0.2)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting || isOtpSubmitting}
              type="password"
              autoComplete="current-password"
              placeholder="Enter your password"
            />
          </label>
          {error && (
            <div className="min-h-[1.1em] text-sm text-[#ff7b72]">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={isSubmitting || isOtpSubmitting || !username.trim() || !password}
            className="w-full rounded-lg bg-[#2f81f7] px-5 py-[11px] text-sm font-semibold tracking-[0.01em] text-white transition-colors hover:bg-[#1f6feb] disabled:cursor-not-allowed disabled:bg-[#4b5563]"
          >
            {isSubmitting ? 'Logging in...' : 'Log in'}
          </button>
        </form>
      </div>

      {preAuth && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-6">
          <form
            onSubmit={submitOtp}
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
                onClick={closeOtp}
                disabled={isOtpSubmitting}
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
                disabled={isOtpSubmitting}
                inputMode="numeric"
                placeholder="Enter OTP code"
              />
            </label>

            {otpError && (
              <div className="mt-3 min-h-[1.1em] text-sm text-[#ff7b72]">
                {otpError}
              </div>
            )}

            <div className="mt-5 flex items-center gap-2">
              <button
                type="button"
                onClick={closeOtp}
                disabled={isOtpSubmitting}
                className="flex-1 rounded-lg border border-[#303741] px-4 py-[10px] text-sm font-medium text-[#9da7b3] transition-colors hover:bg-[#303741] hover:text-[#f0f6fc] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isOtpSubmitting || !otpCode.trim()}
                className="flex-1 rounded-lg bg-[#2f81f7] px-4 py-[10px] text-sm font-semibold text-white transition-colors hover:bg-[#1f6feb] disabled:cursor-not-allowed disabled:bg-[#4b5563]"
              >
                {isOtpSubmitting ? 'Verifying...' : 'Verify'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
