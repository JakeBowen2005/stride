type SyncResult = {
  status?: string;
  new?: number;
  merged?: number;
  message?: string;
  wellness?: { status?: string };
};

type SyncStatus = {
  connected?: boolean;
  last_sync_at?: string | null;
  last_error?: string | null;
  full_sync_job?: {
    state: string;
    status?: string;
    error?: string | null;
    result?: SyncResult | null;
  } | null;
};

/** Wait for the worker's result; queue acceptance is not a completed sync. */
export async function waitForSync(
  read: () => Promise<SyncStatus>,
  signal: AbortSignal,
  pause = () => new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(new Error("Sync cancelled")); return; }
    const abort = () => { clearTimeout(timer); reject(new Error("Sync cancelled")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 2000);
    signal.addEventListener("abort", abort, { once: true });
  }),
): Promise<SyncResult> {
  let initialSync: string | null | undefined;
  for (let attempt = 0; attempt < 120; attempt++) {
    if (signal.aborted) throw new Error("Sync cancelled");
    const status = await read();
    const job = status.full_sync_job;
    if (job?.state === "error") throw new Error(status.last_error || job.error || "Garmin sync failed. Try again in Settings.");
    if (job?.status === "retry" && status.last_error)
      return { status: "backoff", message: status.last_error };
    if (job?.state === "done" && job.result) return job.result;
    // A busy inline sync has no durable job; its status still exposes failures.
    if (!job && status.last_error) throw new Error(status.last_error);
    if (!job && attempt > 0 && status.connected && status.last_sync_at && status.last_sync_at !== initialSync)
      return { status: "ok" };
    if (attempt === 0) initialSync = status.last_sync_at;
    await pause();
  }
  return { status: "pending", message: "Sync is still pending. Check progress in Settings." };
}

export function syncMessage(data: SyncResult): string {
  if (data.status !== "ok") return data.message || "Garmin sync has not completed. Try again shortly.";
  const count = (data.new || 0) + (data.merged || 0);
  const result = count ? `${count} new run${count === 1 ? "" : "s"} from Garmin` : "Runs up to date";
  if (["error", "backoff", "partial"].includes(data.wellness?.status || ""))
    return `${result}; daily health data could not refresh. Try again shortly.`;
  return result;
}
