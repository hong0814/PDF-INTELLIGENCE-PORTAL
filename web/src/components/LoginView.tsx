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
    <div className="flex min-h-screen items-center justify-center bg-[#161b22] px-6 py-8">
      <div className="w-full max-w-[400px] rounded-2xl border border-[#303741] bg-[#212831] px-8 py-9 shadow-[0_4px_24px_rgba(0,0,0,0.35)]">
        <div className="flex flex-col items-center gap-3">
          <img
            alt="분석 Agent 로고"
            className="h-12 w-auto object-contain"
            src="/logo.png"
          />
          <div className="space-y-1 text-center">
            <h1 className="text-[1.2rem] font-semibold text-[#f0f6fc]">분석 Agent</h1>
            <p className="text-sm text-[#9da7b3]">PDF Intelligence Portal</p>
          </div>
        </div>

        <div className="my-5 h-px bg-[#303741]" />

        <form
          className="space-y-4"
          onSubmit={async (event) => {
            event.preventDefault();
            await onSubmit(username, password);
          }}
        >
          <label className="block space-y-1.5">
            <span className="block text-[0.78rem] font-medium tracking-[0.02em] text-[#9da7b3]">ID</span>
            <input
              autoComplete="username"
              className="w-full rounded-[10px] border border-[#303741] bg-[#212831] px-[14px] py-[10px] text-sm text-[#f0f6fc] outline-none transition-[border-color,box-shadow] placeholder:text-[#7d8590] focus:border-[#2f81f7] focus:ring-[3px] focus:ring-[rgba(47,129,247,0.2)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Enter your ID"
              spellCheck={false}
              value={username}
            />
          </label>

          <label className="block space-y-1.5">
            <span className="block text-[0.78rem] font-medium tracking-[0.02em] text-[#9da7b3]">Password</span>
            <input
              autoComplete="current-password"
              className="w-full rounded-[10px] border border-[#303741] bg-[#212831] px-[14px] py-[10px] text-sm text-[#f0f6fc] outline-none transition-[border-color,box-shadow] placeholder:text-[#7d8590] focus:border-[#2f81f7] focus:ring-[3px] focus:ring-[rgba(47,129,247,0.2)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
              type="password"
              value={password}
            />
          </label>

          {error && (
            <div className="min-h-[1.1em] text-sm text-[#ff7b72]">
              {error}
            </div>
          )}

          <button
            className="w-full rounded-lg bg-[#2f81f7] px-5 py-[11px] text-sm font-semibold tracking-[0.01em] text-white transition-colors hover:bg-[#1f6feb] disabled:cursor-not-allowed disabled:bg-[#4b5563]"
            disabled={isSubmitting || !username.trim() || !password}
            type="submit"
          >
            {isSubmitting ? 'Logging in...' : 'Log in'}
          </button>
        </form>
      </div>
    </div>
  );
}
