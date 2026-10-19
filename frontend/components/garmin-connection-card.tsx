"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { GarminSync } from "@/components/garmin-sync";

const API = process.env.NEXT_PUBLIC_API_URL || "";

interface Status {
  tokens_present: boolean;
  connected: boolean;
  display_name: string | null;
  last_sync_at: string | null;
  last_new_activity_at: string | null;
  last_error: string | null;
  full_sync_done: boolean;
  full_sync_job: { state: "running" | "done" | "error"; result: unknown } | null;
}

export function GarminConnectionCard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [offline, setOffline] = useState(false);

  async function load() {
    try {
      const res = await fetch(`${API}/api/garmin/status/1`);
      setStatus(await res.json());
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }

  useEffect(() => {
    const id = setTimeout(load, 0);
    return () => clearTimeout(id);
  }, []);

  // Poll while a full history import is running
  const running = status?.full_sync_job?.state === "running";
  useEffect(() => {
    if (!running) return;
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [running]);

  async function fullSync() {
    await fetch(`${API}/api/garmin/full-sync/1`, { method: "POST" });
    load();
  }

  const job = status?.full_sync_job;

  return (
    <Card>
      <CardContent className="space-y-4 pt-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Garmin Connect</h2>
          {status?.tokens_present ? (
            <Badge variant="secondary" className="text-xs">
              Connected{status.display_name ? ` · ${status.display_name}` : ""}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-xs">
              Not connected
            </Badge>
          )}
        </div>

        {offline && <p className="text-sm text-destructive">Can&apos;t reach the Stride backend.</p>}

        {status && !status.tokens_present && (
          <div className="space-y-2 rounded-md bg-secondary/40 p-3 text-sm">
            <p className="font-medium">Connect once from your computer:</p>
            <pre className="overflow-x-auto rounded bg-background p-2 text-xs">
              cd backend{"\n"}venv/bin/python garmin_login.py
            </pre>
            <p className="text-muted-foreground">
              Enter your Garmin email, password and MFA code there. Only a session token is saved — then come back and
              tap Sync.
            </p>
          </div>
        )}

        {status?.tokens_present && (
          <>
            <div className="flex items-start justify-between gap-4 text-sm">
              <div className="space-y-1 text-muted-foreground">
                <p>New runs sync automatically every few minutes while Stride is running, and whenever you open the app.</p>
                {status.last_error && <p className="text-destructive">{status.last_error}</p>}
              </div>
              <GarminSync autoSync={false} label="Sync now" onNewActivities={load} />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" onClick={fullSync} disabled={running}>
                {running ? "Importing full history…" : "Re-import full Garmin history"}
              </Button>
              {job?.state === "done" && (
                <span className="text-xs text-muted-foreground">
                  {(job.result as { message?: string })?.message ?? "Done"}
                </span>
              )}
              {job?.state === "error" && <span className="text-xs text-destructive">{String(job.result)}</span>}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
