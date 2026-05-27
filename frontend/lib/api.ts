const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  // Onboarding
  submitOnboarding: (data: unknown) =>
    request("/api/onboarding", { method: "POST", body: JSON.stringify(data) }),

  getStravaAuthUrl: () =>
    request<{ url: string }>("/api/strava/auth-url"),

  // User
  getUser: () => request<unknown>("/api/user"),

  // Plan
  getCurrentPlan: () => request<unknown>("/api/plan/current"),
  getTodayWorkout: () => request<unknown>("/api/plan/today"),
  getCurrentWeek: () => request<unknown>("/api/plan/week/current"),
  generateNextPlan: () =>
    request<unknown>("/api/plan/generate", { method: "POST" }),
  approvePlan: (planId: number) =>
    request<unknown>(`/api/plan/approve/${planId}`, { method: "PUT" }),
  swapDays: (dayA: number, dayB: number) =>
    request<unknown>("/api/plan/swap-days", {
      method: "PUT",
      body: JSON.stringify({ day_a: dayA, day_b: dayB }),
    }),
  skipDay: (dayId: number, reason?: string) =>
    request<unknown>(`/api/plan/skip-day/${dayId}`, {
      method: "PUT",
      body: JSON.stringify({ reason }),
    }),

  // Activities
  getActivities: (params?: { type?: string; search?: string; page?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.type) searchParams.set("type", params.type);
    if (params?.search) searchParams.set("search", params.search);
    if (params?.page) searchParams.set("page", String(params.page));
    return request<unknown>(`/api/activities?${searchParams}`);
  },
  getActivity: (id: number) => request<unknown>(`/api/activities/${id}`),
  getRecentActivity: () => request<unknown>("/api/activities/recent?limit=1"),
  submitReview: (id: number, data: { feel_rating: number; notes?: string }) =>
    request<unknown>(`/api/activities/${id}/review`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Stats
  getWeeklyMileage: (weeks = 8) =>
    request<unknown>(`/api/stats/weekly-mileage?weeks=${weeks}`),
  getPaceVsTarget: (limit = 6) =>
    request<unknown>(`/api/stats/pace-vs-target?limit=${limit}`),
  getMileageOverTime: (weeks = 12) =>
    request<unknown>(`/api/stats/mileage-over-time?weeks=${weeks}`),
  getLongRunProgression: (weeks = 12) =>
    request<unknown>(`/api/stats/long-run-progression?weeks=${weeks}`),
};
