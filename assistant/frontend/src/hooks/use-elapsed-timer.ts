"use client";

import { useEffect, useRef, useState } from "react";

export function useElapsedTimer(running: boolean, startedAt?: number | null) {
  const getElapsed = () => {
    if (!running || !startedAt) {
      return 0;
    }
    return Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  };

  const [elapsed, setElapsed] = useState(getElapsed);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (running) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync display to persisted start time
      setElapsed(getElapsed());
      timerRef.current = setInterval(() => {
        setElapsed(getElapsed());
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [running, startedAt]);

  const formatTime = (s: number) => {
    const min = Math.floor(s / 60);
    const sec = s % 60;
    // TODO(i18n): extract "分" and "秒" to locale file
    return min > 0 ? `${min}分${sec}秒` : `${sec}秒`;
  };

  return { elapsed, formatted: formatTime(elapsed) };
}
