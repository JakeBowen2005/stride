"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import Link from "next/link";
import { syncMessage, waitForSync } from "@/lib/garmin-sync";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";


interface GarminStatus {
  api_key_present: boolean;
  connected: boolean;
  connection_issue?: string | null;
  display_name: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  full_sync_done: boolean;
}

/** Fired after a sync brings in new runs so every open view can reload. */
export const SYNC_EVENT = "stride:synced";

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

/**
 * Garmin sync button + status. Also syncs automatically when the app is opened
 * or brought back to the foreground, so a run you just finished shows up
 * without tapping anything. Calls onNewActivities when new runs arrived.
 */
export function GarminSync({
  onNewActivities,
  autoSync = true,
  label = "Sync Garmin",
  variant = "default",
}: {
  onNewActivities?: () => void;
  autoSync?: boolean;
  label?: string;
  variant?: "default" | "bar";
}) {
  const [status, setStatus] = useState<GarminStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const lastAutoSync = useRef(0);
  const inFlight = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const onRefresh = useRef(onNewActivities);
  useEffect(() => { onRefresh.current = onNewActivities; }, [onNewActivities]);
  useEffect(() => () => controller.current?.abort(), []);

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetch(apiUrl(`/garmin/status/${USER_ID}`));
      if (res.ok) setStatus(await res.json());
    } catch {
      /* backend offline — handled on sync */
    }
  }, []);

  const sync = useCallback(
    async () => {
      if (inFlight.current) return;
      inFlight.current = true;
      controller.current = new AbortController();
      const signal = controller.current.signal;
      setSyncing(true);
      setMessage(null);
      try {
        const res = await fetch(apiUrl(`/garmin/sync/${USER_ID}`), { method: "POST", signal });
        let data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Sync failed");
        if (data.state === "running" || data.status === "busy") {
          setMessage("Syncing with Garmin…");
          data = await waitForSync(async () => {
            const response = await fetch(apiUrl(`/garmin/status/${USER_ID}`), { signal });
            if (!response.ok) throw new Error("Could not check Garmin sync status");
            const next = await response.json();
            setStatus(next);
            return next;
          }, signal);
        }
        if (signal.aborted) return;
        setMessage(syncMessage(data));
        if (data.status === "ok") {
          onRefresh.current?.();
          window.dispatchEvent(new Event(SYNC_EVENT));
        }
      } catch (error) {
        if (!signal.aborted) setMessage(error instanceof Error ? error.message : "Can't reach Stride backend");
      } finally {
        inFlight.current = false;
        if (!signal.aborted) {
          setSyncing(false);
          loadStatus();
        }
      }
    },
    [loadStatus],
  );

  useEffect(() => {
    const initial = setTimeout(() => {
      loadStatus();
      if (autoSync) maybeSync();
    }, 0);
    const maybeSync = () => {
      // At most once a minute, only when visible
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastAutoSync.current < 60_000) return;
      lastAutoSync.current = Date.now();
      sync();
    };
    window.addEventListener(SYNC_EVENT, loadStatus);
    if (autoSync) document.addEventListener("visibilitychange", maybeSync);
    return () => {
      clearTimeout(initial);
      document.removeEventListener("visibilitychange", maybeSync);
      window.removeEventListener(SYNC_EVENT, loadStatus);
    };
  }, [autoSync, loadStatus, sync]);

  const notConnected = status && !status.api_key_present;

  if (variant === "bar") {
    const healthy = status?.connected && !status.last_error;
    return (
      <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
        <span aria-hidden="true" className="dot" style={{ background: healthy ? "var(--status-good)" : "var(--status-serious)" }} />
        <span className="truncate"><span className="sr-only">Garmin: </span><span aria-hidden="true" className="max-md:hidden">Garmin · </span>{message ?? (notConnected ? "not connected" : `synced ${timeAgo(status?.last_sync_at ?? null)}`)}</span>
        {notConnected ? <Link href="/settings" className="shrink-0 rounded-full px-2 py-1 font-semibold text-foreground underline-offset-2 hover:underline">Connect</Link> :
          <button type="button" onClick={() => sync()} disabled={syncing}
            className="min-h-8 shrink-0 rounded-full px-2.5 font-semibold text-foreground transition-colors hover:bg-[var(--row-hover)] disabled:opacity-60">{syncing ? "Syncing…" : "Sync now"}</button>}
      </div>
    );
  }

  if (notConnected) {
    return (
      <div className="flex max-w-sm flex-col items-end gap-1">
        <Link href="/settings#garmin" className="inline-flex min-h-10 items-center rounded-full border border-[var(--glass-border)] bg-[var(--glass-inner)] px-3.5 text-xs font-semibold">
          {status?.last_sync_at ? "Reconnect Garmin" : "Connect Garmin"}
        </Link>
        <span className="text-right text-xs text-muted-foreground">{status?.connection_issue || "Garmin needs to be connected in Settings."}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="outline" size="sm" className="h-10 sm:h-8" onClick={() => sync()} disabled={syncing}>
        {syncing ? "Syncing…" : label}
      </Button>
      {notConnected || (status?.last_error && !message) ? (
        <Link href="/settings" className="text-right text-xs text-muted-foreground underline underline-offset-2">
          {status?.last_sync_at ? `Synced ${timeAgo(status.last_sync_at)} · ` : ""}
          {notConnected ? "reconnect Garmin" : "last sync failed"}
        </Link>
      ) : (
        <span className="text-xs text-muted-foreground">
          {message ?? `Synced ${timeAgo(status?.last_sync_at ?? null)}`}
        </span>
      )}
    </div>
  );
}

export function useGarminStatus() {
  const [status, setStatus] = useState<GarminStatus | null>(null);
  useEffect(() => {
    fetch(apiUrl(`/garmin/status/${USER_ID}`))
      .then((r) => (r.ok ? r.json() : null))
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);
  return status;
}
