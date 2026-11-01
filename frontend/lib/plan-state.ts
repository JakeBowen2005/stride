import { getJson, USER_ID } from './api';

export async function loadPlanState<T>() {
  const [active, preview, next] = await Promise.all([
    getJson<T>(`/plans/${USER_ID}/current`, { allowNotFound: true }),
    getJson<T>(`/plans/${USER_ID}/draft?scope=current`),
    getJson<T>(`/plans/${USER_ID}/draft?scope=next`),
  ]);
  return { active, preview, next, visible: preview ?? active };
}

export interface NextPreview {
  state: "hidden" | "upcoming" | "available" | "ready" | "blocked";
  opens_on: string;
  next_start: string;
  next_end: string;
  provisional: boolean;
  reason?: string;
  draft_id?: number | null;
  stale: boolean;
}
