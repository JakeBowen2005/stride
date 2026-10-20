import { getJson, USER_ID } from './api';

export async function loadPlanState<T>() {
  const [active, preview] = await Promise.all([
    getJson<T>(`/plans/${USER_ID}/current`, { allowNotFound: true }),
    getJson<T>(`/plans/${USER_ID}/draft`),
  ]);
  return { active, preview, visible: preview ?? active };
}

export function nextBlockAvailable(endDate: string, today: string): boolean {
  return today > endDate;
}
