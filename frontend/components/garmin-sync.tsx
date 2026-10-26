"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";


interface GarminStatus {
  api_key_present: boolean;
  connected: boolean;
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

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetch(apiUrl(`/garmin/status/${USER_ID}`));
      if (res.ok) setStatus(await res.json());
    } catch {
      /* backend offline — handled on sync */
    }
  }, []);

  const sync = useCallback(
    async (manual: boolean) => {
      setSyncing(true);
      if (manual) setMessage(null);
      try {
        const res = await fetch(apiUrl(`/garmin/sync/${USER_ID}`), { method: "POST" });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          if (data.status === "busy") {
            if (manual) setMessage("Sync already running…");
          } else if ((data.new || 0) + (data.merged || 0) > 0) {
            setMessage(`${data.new + data.merged} new run${data.new + data.merged === 1 ? "" : "s"} from Garmin`);
            onNewActivities?.();
            window.dispatchEvent(new Event(SYNC_EVENT));
          } else if (data.wellness?.status === "ok") {
            // No new run, but sleep/HRV/readiness refreshed — reload what's on screen
            onNewActivities?.();
            if (manual) setMessage("Up to date");
          } else if (manual) {
            setMessage("Up to date");
          }
        } else if (res.status === 409) {
          setMessage(null); // status line below explains it
        } else if (manual) {
          setMessage(data.detail || "Sync failed");
        }
      } catch {
        if (manual) setMessage("Can't reach Stride backend");
      } finally {
        setSyncing(false);
        loadStatus();
      }
    },
    [loadStatus, onNewActivities],
  );

  useEffect(() => {
    const initial = setTimeout(() => {
      loadStatus();
      if (autoSync) maybeSync();
    }, 0);
    if (!autoSync) return () => clearTimeout(initial);
    const maybeSync = () => {
      // At most once a minute, only when visible
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastAutoSync.current < 60_000) return;
      lastAutoSync.current = Date.now();
      sync(false);
    };
    document.addEventListener("visibilitychange", maybeSync);
    return () => {
      clearTimeout(initial);
      document.removeEventListener("visibilitychange", maybeSync);
    };
  }, [autoSync, loadStatus, sync]);

  const notConnected = status && !status.api_key_present;

  if (variant === "bar") {
    const healthy = status?.api_key_present && !status.last_error;
    return (
      <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
        <span aria-hidden="true" className="dot" style={{ background: healthy ? "var(--status-good)" : "var(--status-serious)" }} />
        <span className="truncate"><span className="sr-only">Garmin: </span><span aria-hidden="true" className="max-md:hidden">Garmin · </span>{message ?? (notConnected ? "not connected" : `synced ${timeAgo(status?.last_sync_at ?? null)}`)}</span>
        {notConnected ? <Link href="/settings" className="shrink-0 rounded-full px-2 py-1 font-semibold text-foreground underline-offset-2 hover:underline">Connect</Link> :
          <button type="button" onClick={() => sync(true)} disabled={syncing}
            className="min-h-8 shrink-0 rounded-full px-2.5 font-semibold text-foreground transition-colors hover:bg-[var(--row-hover)] disabled:opacity-60">{syncing ? "Syncing…" : "Sync now"}</button>}
      </div>
    );
  }

  // Watchless athletes (no key ever set up) get a quiet link, not a disabled sync button
  if (notConnected && !status?.last_sync_at) {
    return (
      <Link href="/settings" className="text-xs text-muted-foreground underline underline-offset-2">Connect Garmin</Link>
    );
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="outline" size="sm" className="h-10 sm:h-8" onClick={() => sync(true)} disabled={syncing || !!notConnected}>
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
