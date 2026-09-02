import { useEffect, useRef } from "react";

/** Polling job status mỗi `intervalMs` (mục 3: 2 giây) — dừng khi `enabled=false`
 * (vd job đã 'done'/'failed', không cần poll tiếp). */
export function usePolling(callback: () => void, intervalMs: number, enabled: boolean) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => savedCallback.current(), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);
}
