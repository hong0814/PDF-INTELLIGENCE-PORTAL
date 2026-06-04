import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../api/client';
import type { AuthConfig } from '../types';

const ACTIVITY_EVENTS = ['mousemove', 'click', 'keydown', 'scroll', 'touchstart'] as const;
const SERVER_TOUCH_INTERVAL_MS = 30_000;

interface SessionTimeoutGuardProps {
  config: AuthConfig;
  onExpired: () => void;
}

function formatRemaining(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

export default function SessionTimeoutGuard({ config, onExpired }: SessionTimeoutGuardProps) {
  const idleMs = Math.max(1, config.idle_timeout_seconds) * 1000;
  const warnMs = Math.min(idleMs, Math.max(0, config.warn_before_seconds) * 1000);
  const [lastActivity, setLastActivity] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const expiringRef = useRef(false);
  const lastTouchRef = useRef(0);

  const remainingMs = useMemo(
    () => Math.max(0, idleMs - (now - lastActivity)),
    [idleMs, lastActivity, now],
  );
  const isWarning = remainingMs > 0 && remainingMs <= warnMs;
  const isPreWarning = !isWarning && warnMs > 0 && remainingMs <= warnMs * 2;
  const badgeClass = isWarning
    ? 'bg-danger/10 text-danger opacity-100 font-bold'
    : isPreWarning
      ? 'bg-warning/10 text-warning opacity-90 font-semibold'
      : 'bg-black/[0.08] text-text-muted opacity-70 font-normal';

  const expire = useCallback(async () => {
    if (expiringRef.current) return;
    expiringRef.current = true;
    try {
      await api.logout();
    } catch {
      // The local transition to the login screen is the important part here.
    } finally {
      onExpired();
    }
  }, [onExpired]);

  const touch = useCallback(async (force = false) => {
    if (expiringRef.current) return;
    const current = Date.now();
    setLastActivity(current);
    setNow(current);
    if (!force && current - lastTouchRef.current < SERVER_TOUCH_INTERVAL_MS) return;
    lastTouchRef.current = current;
    try {
      await api.touchAuth();
    } catch {
      expiringRef.current = true;
      onExpired();
    }
  }, [onExpired]);

  useEffect(() => {
    const onActivity = () => { void touch(false); };
    ACTIVITY_EVENTS.forEach((event) => window.addEventListener(event, onActivity, { passive: true }));
    return () => ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, onActivity));
  }, [touch]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (remainingMs <= 0) {
      void expire();
    }
  }, [expire, remainingMs]);

  useEffect(() => {
    const onAuthExpired = () => {
      expiringRef.current = true;
      onExpired();
    };
    window.addEventListener(api.AUTH_EXPIRED_EVENT, onAuthExpired);
    return () => window.removeEventListener(api.AUTH_EXPIRED_EVENT, onAuthExpired);
  }, [onExpired]);

  return (
    <>
      <div
        aria-live="polite"
        aria-label={`세션 남은 시간 ${formatRemaining(remainingMs)}`}
        className={`pointer-events-none fixed bottom-3 right-3 z-50 rounded-xl px-[9px] py-1 font-mono text-[11px] leading-4 shadow-sm transition-[background,color,opacity] duration-300 ${badgeClass}`}
      >
        Session: {formatRemaining(remainingMs)}
      </div>

      {isWarning && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/35 px-6">
          <div className="w-full max-w-[360px] rounded-lg bg-surface-elevated border border-border shadow-xl p-5">
            <h2 className="text-base font-semibold text-text-primary mb-2">세션 만료 예정</h2>
            <p className="text-sm text-text-secondary mb-5">
              입력이 없으면 {formatRemaining(remainingMs)} 후 로그인 화면으로 돌아갑니다.
            </p>
            <button
              type="button"
              onClick={() => { void touch(true); }}
              className="w-full h-10 rounded-md bg-primary text-white font-semibold hover:bg-primary-hover transition-colors"
            >
              계속 사용
            </button>
          </div>
        </div>
      )}
    </>
  );
}
