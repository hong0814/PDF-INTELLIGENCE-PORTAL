import { useState, type FormEvent } from 'react';
import * as api from '../api/client';
import type { AuthStatus } from '../types';

interface LoginScreenProps {
  onLogin: (status: AuthStatus) => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) return;
    setError('');
    setIsSubmitting(true);
    try {
      const status = await api.loginWithLdap(username.trim(), password);
      onLogin(status);
    } catch {
      setError('아이디 또는 비밀번호를 확인하세요.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center px-6">
      <div className="w-full max-w-[380px]">
        <div className="mb-7">
          <div className="w-12 h-12 rounded-lg bg-primary text-white flex items-center justify-center mb-4">
            <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-text-primary">PDF Intelligence Portal</h1>
          <p className="mt-2 text-sm text-text-secondary">문서 분석 작업을 계속하려면 로그인하세요.</p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="block text-sm font-medium text-text-secondary mb-1.5">아이디</span>
            <input
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full h-11 px-3 rounded-md border border-border bg-surface-elevated text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
              autoComplete="username"
            />
          </label>
          <label className="block">
            <span className="block text-sm font-medium text-text-secondary mb-1.5">비밀번호</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full h-11 px-3 rounded-md border border-border bg-surface-elevated text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
              type="password"
              autoComplete="current-password"
            />
          </label>
          {error && (
            <div className="rounded-md border border-danger/20 bg-danger/5 px-3 py-2 text-sm text-danger">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={isSubmitting || !username.trim() || !password}
            className="w-full h-11 rounded-md bg-primary text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed hover:bg-primary-hover transition-colors"
          >
            {isSubmitting ? '로그인 중...' : '로그인'}
          </button>
        </form>
      </div>
    </div>
  );
}
