import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../api/client';
import type { AuthConfig } from '../types';

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
  const warnMs = Math.max(0, config.warn_before_seconds) * 1000;
  const [lastActivity, setLastActivity] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [isExpiring, setIsExpiring] = useState(false);
  const lastTouchRef = useRef(0);

  const remainingMs = useMemo(
    () => Math.max(0, idleMs - (now - lastActivity)),
    [idleMs, lastActivity, now],
  );
  const isWarning = remainingMs > 0 && remainingMs <= warnMs;

  const expire = useCallback(async () => {
    if (isExpiring) return;
    setIsExpiring(true);
    try {
      await api.logout();
    } catch {
      // The local transition to the login screen is the important part here.
    } finally {
      onExpired();
    }
  }, [isExpiring, onExpired]);

  const touch = useCallback(async (force = false) => {
    const current = Date.now();
    setLastActivity(current);
    setNow(current);
    if (!force && current - lastTouchRef.current < 30000) return;
    lastTouchRef.current = current;
    try {
      await api.touchAuth();
    } catch {
      onExpired();
    }
  }, [onExpired]);

  useEffect(() => {
    const events = ['mousemove', 'click', 'keydown', 'scroll', 'touchstart'];
    const onActivity = () => { void touch(false); };
    events.forEach((event) => window.addEventListener(event, onActivity, { passive: true }));
    return () => events.forEach((event) => window.removeEventListener(event, onActivity));
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
    const onAuthExpired = () => onExpired();
    window.addEventListener(api.AUTH_EXPIRED_EVENT, onAuthExpired);
    return () => window.removeEventListener(api.AUTH_EXPIRED_EVENT, onAuthExpired);
  }, [onExpired]);

  return (
    <>
      <div className={`fixed bottom-4 right-4 z-50 rounded-md border px-3 py-2 text-xs shadow-sm ${
        isWarning
          ? 'border-warning/30 bg-warning/10 text-warning'
          : 'border-border bg-surface-elevated text-text-secondary'
      }`}>
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
