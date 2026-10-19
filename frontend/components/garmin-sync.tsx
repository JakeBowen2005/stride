"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";


interface GarminStatus {
  tokens_present: boolean;
  connected: boolean;
  display_name: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  full_sync_done: boolean;
}

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
}: {
  onNewActivities?: () => void;
  autoSync?: boolean;
  label?: string;
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

  const notConnected = status && !status.tokens_present;

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="outline" size="sm" onClick={() => sync(true)} disabled={syncing || !!notConnected}>
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
