import { useState, useCallback } from 'react';
import { GraphSettings, DEFAULT_SETTINGS } from '../types';

const STORAGE_KEY = 'mimir_graph_settings';

function loadSettings(): GraphSettings {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function saveSettings(settings: GraphSettings): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // SessionStorage quota exceeded — fail silently
  }
}

export function useGraphSettings() {
  const [settings, setSettings] = useState<GraphSettings>(loadSettings);

  const updateSettings = useCallback((patch: Partial<GraphSettings>) => {
    setSettings(prev => {
      const next = { ...prev, ...patch };
      saveSettings(next);
      return next;
    });
  }, []);

  return [settings, updateSettings] as const;
}
