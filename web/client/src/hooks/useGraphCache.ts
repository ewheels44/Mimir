import { useCallback } from 'react';
import { GraphData } from '../types';

const TTL_MS = 5 * 60 * 1000; // 5 minutes
const SERVER_KEY_STORAGE = 'mimir_server_cache_key';

interface CacheEntry {
  data: GraphData & { viewport?: { zoom: number; pan: { x: number; y: number } } };
  timestamp: number;
  serverKey: string;
}

function cacheKey(minDegree: number, layout: string) {
  return `mimir_graph_${minDegree}_${layout}`;
}

function invalidateAll() {
  const toRemove: string[] = [];
  for (let i = 0; i < sessionStorage.length; i++) {
    const k = sessionStorage.key(i);
    if (k?.startsWith('mimir_graph_')) toRemove.push(k);
  }
  toRemove.forEach(k => sessionStorage.removeItem(k));
  sessionStorage.removeItem(SERVER_KEY_STORAGE);
}

export function useGraphCache() {
  /** Check server cache key; if changed, blow away all client caches. Returns whether a refresh is needed. */
  const checkServerKey = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch('/api/graph/cache-key');
      if (!res.ok) return false;
      const serverKey: string = await res.json();
      const stored = sessionStorage.getItem(SERVER_KEY_STORAGE);
      if (serverKey !== stored) {
        invalidateAll();
        sessionStorage.setItem(SERVER_KEY_STORAGE, serverKey);
        return true; // stale — must re-fetch
      }
      return false; // still valid
    } catch {
      return false;
    }
  }, []);

  const get = useCallback(
    (minDegree: number, layout: string): CacheEntry['data'] | null => {
      try {
        const raw = sessionStorage.getItem(cacheKey(minDegree, layout));
        if (!raw) return null;
        const entry: CacheEntry = JSON.parse(raw);
        if (Date.now() - entry.timestamp > TTL_MS) {
          sessionStorage.removeItem(cacheKey(minDegree, layout));
          return null;
        }
        return entry.data;
      } catch {
        return null;
      }
    },
    []
  );

  const set = useCallback(
    (
      minDegree: number,
      layout: string,
      data: CacheEntry['data']
    ) => {
      try {
        const serverKey = sessionStorage.getItem(SERVER_KEY_STORAGE) ?? '';
        const entry: CacheEntry = { data, timestamp: Date.now(), serverKey };
        sessionStorage.setItem(cacheKey(minDegree, layout), JSON.stringify(entry));
      } catch {
        // Quota exceeded — don't crash, just skip caching
      }
    },
    []
  );

  return { get, set, checkServerKey };
}
