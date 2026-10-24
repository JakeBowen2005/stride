"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { GarminSync } from "@/components/garmin-sync";


interface Status {
  api_key_present: boolean;
  business_pending?: boolean;
  owner_key_storage_ready?: boolean;
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
  const [connectionMessage,setConnectionMessage]=useState("");
  const [offline, setOffline] = useState(false);

  async function load() {
    try {
      const res = await fetch(apiUrl(`/garmin/status/${USER_ID}`));
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
    await fetch(apiUrl(`/garmin/full-sync/${USER_ID}`), { method: "POST" });
    load();
  }

  const job = status?.full_sync_job;

  return (
    <Card>
      <CardContent className="space-y-4 pt-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Garmin Connect</h2>
          {status?.api_key_present && !status.connected && status.last_error ? (
            <Badge variant="destructive" className="text-xs">Needs attention</Badge>
          ) : status?.api_key_present ? (
            <Badge variant="secondary" className="text-xs">
              Connected{status.display_name ? ` · ${status.display_name}` : ""}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-xs">
              Not set up
            </Badge>
          )}
        </div>

        {offline && <p className="text-sm text-destructive">Can&apos;t reach the Stride backend.</p>}

        {status?.business_pending && <p className="text-sm">Separate Garmin connections are awaiting Business API approval. Import your original FIT files below to build your history now.</p>}
        {status && !status.api_key_present && !status.business_pending && (
          <div className="space-y-2 rounded-md bg-secondary/40 p-3 text-sm">
            <p className="font-medium">Connect Garmin with a Personal API key.</p>
            <p className="text-muted-foreground">
              Create a key in Garmin Connect (Settings → Personal API Key), then add it to the Stride server as{" "}
              <code>GARMIN_API_KEY</code> and restart. Keys last 30 days to a year; Garmin emails you before one expires.
            </p>
            <a
              className="text-sm underline underline-offset-2"
              href="https://connect.garmin.com/app/settings/personalApiToken"
              target="_blank"
              rel="noreferrer"
            >
              Open Garmin&apos;s Personal API Key page
            </a>
          </div>
        )}

        {status?.owner_key_storage_ready && <form className="space-y-2" onSubmit={async e=>{e.preventDefault();const form=e.currentTarget;const f=new FormData(form);const r=await fetch(apiUrl(`/garmin/connect/${USER_ID}`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:f.get('key')})});const d=await r.json();setConnectionMessage(r.ok?d.message:typeof d.detail==='string'?d.detail:'Could not save key.');if(r.ok){form.reset();load();}}}><label className="block text-sm">Your owner Personal API key<input className="block min-h-11 w-full rounded border p-2" name="key" type="password" required autoComplete="off"/></label><Button type="submit" variant="outline">Save encrypted key</Button></form>}
        {connectionMessage && <p role="status" className="text-sm">{connectionMessage}</p>}
        {status?.api_key_present && <Button variant="outline" onClick={async()=>{const r=await fetch(apiUrl(`/garmin/disconnect/${USER_ID}`),{method:'POST'});if(r.ok){setConnectionMessage('Disconnected. Revoke the key in Garmin to finish removal there.');load();}}}>Disconnect Garmin</Button>}
        {status?.api_key_present && (
          <>
            <div className="flex items-start justify-between gap-4 text-sm">
              <div className="space-y-1 text-muted-foreground">
                <p>New runs sync whenever you open the app, and Stride checks Garmin every 15 minutes in the background (hourly overnight).</p>
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
