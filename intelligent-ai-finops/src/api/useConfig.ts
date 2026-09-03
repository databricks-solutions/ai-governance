import { useEffect, useState } from 'react';
import type { AppConfig } from './types';
import { getConfig } from './client';

let cache: AppConfig | null = null;

// Fetch /api/config once and share it. Models and prices come from here, never
// hardcoded in a component (§4).
export function useConfig(): AppConfig | null {
  const [cfg, setCfg] = useState<AppConfig | null>(cache);
  useEffect(() => {
    if (cache) return;
    getConfig()
      .then((c) => {
        cache = c;
        setCfg(c);
      })
      .catch(() => setCfg(null));
  }, []);
  return cfg;
}
