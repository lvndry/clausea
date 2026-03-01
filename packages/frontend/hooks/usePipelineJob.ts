"use client";

import { useCallback, useState } from "react";

const STORAGE_KEY = "clausea:activeJobId";

/**
 * Persists the active pipeline job ID in localStorage so in-progress
 * analyses survive page refreshes and tab closes.
 *
 * Call `clearJobId()` once the job reaches a terminal state
 * (completed / failed / dismissed).
 */
export function usePipelineJob() {
  const [jobId, setJobIdState] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const setJobId = useCallback((id: string) => {
    localStorage.setItem(STORAGE_KEY, id);
    setJobIdState(id);
  }, []);

  const clearJobId = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setJobIdState(null);
  }, []);

  return { jobId, setJobId, clearJobId };
}
