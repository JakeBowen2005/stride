"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { apiUrl, USER_ID } from "@/lib/api";
import type { Units } from "@/lib/units";

export const PREFERENCES_EVENT = "stride:preferences-changed";
const ClockContext = createContext<string | undefined>(undefined);
const UnitsContext = createContext<Units>("miles");

/** Display preference only; canonical API distances remain miles. No provider calls. */
export function UnitPreferences({ children }: { children: React.ReactNode }) {
  const [timezone, setTimezone] = useState<string | undefined>();
  const [units, setUnits] = useState<Units>("miles");
  const path = usePathname();
  useEffect(() => {
    if (path.startsWith("/login")) return;
    const abort = new AbortController();
    const load = () => {
      fetch(apiUrl(`/users/${USER_ID}`), { signal: abort.signal }).then(async response => {
        if (response.ok) { const user = await response.json(); setTimezone(user.timezone || undefined); setUnits(user.units === "km" ? "km" : "miles"); }
      }).catch(() => { /* The page's normal data loader exposes connection errors. */ });
    };
    load();
    window.addEventListener(PREFERENCES_EVENT, load);
    return () => { abort.abort(); window.removeEventListener(PREFERENCES_EVENT, load); };
  }, [path]);
  return <ClockContext.Provider value={timezone}><UnitsContext.Provider value={units}>{children}</UnitsContext.Provider></ClockContext.Provider>;
}
export const useUnits = () => useContext(UnitsContext);

export function useAthleteToday() {
  const timezone=useContext(ClockContext);
  const d=new Date();
  return timezone ? new Intl.DateTimeFormat("en-CA",{timeZone:timezone,year:"numeric",month:"2-digit",day:"2-digit"}).format(d) : `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
