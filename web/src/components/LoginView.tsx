import { useState } from 'react';

interface LoginViewProps {
  error: string | null;
  isSubmitting: boolean;
  onSubmit: (username: string, password: string) => Promise<void>;
}

export default function LoginView({ error, isSubmitting, onSubmit }: LoginViewProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center px-6">
      <div className="w-full max-w-md bg-surface-elevated border border-border rounded-2xl shadow-xl shadow-black/5 p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-11 h-11 rounded-2xl bg-primary text-white flex items-center justify-center">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 0h10.5A2.25 2.25 0 0119.5 12.75v6A2.25 2.25 0 0117.25 21h-10.5A2.25 2.25 0 014.5 18.75v-6A2.25 2.25 0 016.75 10.5z" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-semibold text-text-primary">LDAP 로그인</h1>
            <p className="text-sm text-text-muted">사내 계정으로 PDF Intelligence Portal에 접속합니다.</p>
          </div>
        </div>

        <form
          className="space-y-4"
          onSubmit={async (event) => {
            event.preventDefault();
            await onSubmit(username, password);
          }}
        >
          <label className="block">
            <span className="block text-sm font-medium text-text-secondary mb-1.5">아이디</span>
            <input
              autoComplete="username"
              className="w-full rounded-xl border border-border bg-surface px-3.5 py-3 text-sm text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              disabled={isSubmitting}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="사번 또는 LDAP 아이디"
              value={username}
            />
          </label>

          <label className="block">
            <span className="block text-sm font-medium text-text-secondary mb-1.5">비밀번호</span>
            <input
              autoComplete="current-password"
              className="w-full rounded-xl border border-border bg-surface px-3.5 py-3 text-sm text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              disabled={isSubmitting}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="비밀번호"
              type="password"
              value={password}
            />
          </label>

          {error && (
            <div className="rounded-xl border border-danger/20 bg-danger/5 px-3.5 py-3 text-sm text-danger">
              {error}
            </div>
          )}

          <button
            className="w-full rounded-xl bg-primary text-white py-3 text-sm font-medium hover:bg-primary-hover transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            disabled={isSubmitting || !username.trim() || !password}
            type="submit"
          >
            {isSubmitting ? '로그인 중...' : '로그인'}
          </button>
        </form>
      </div>
    </div>
  );
}
