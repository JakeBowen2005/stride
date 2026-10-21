export interface ReviewStateInput { stale: boolean; status: "pending" | "ready" | "fallback"; applied_candidate_id: string | null; suggestions: unknown[] }
export function coachingState(review: ReviewStateInput | null, job: string | null, busy = false): string {
  if (busy || job === "running" || review?.status === "pending") return "Review in progress";
  if (job === "waiting_sync" || job === "queued") return "Run synced · review queued";
  if (review?.stale) return "Outdated advice · training or settings changed";
  if (review?.status === "fallback") return "Rules-based fallback · AI unavailable";
  if (review?.applied_candidate_id) return "Change applied · review updated training before another change";
  if (review?.suggestions.length) return "Current review · awaiting your approval";
  if (review?.status === "ready") return "Current review · no changes suggested";
  if (job === "failed") return "Automatic review failed · manual review available";
  return "No review yet";
}
