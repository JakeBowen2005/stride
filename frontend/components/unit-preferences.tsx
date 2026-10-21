"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { apiUrl, USER_ID } from "@/lib/api";
import type { Units } from "@/lib/units";

export const PREFERENCES_EVENT = "stride:preferences-changed";
const UnitsContext = createContext<Units>("miles");

/** Display preference only; canonical API distances remain miles. No provider calls. */
export function UnitPreferences({ children }: { children: React.ReactNode }) {
  const [units, setUnits] = useState<Units>("miles");
  const path = usePathname();
  useEffect(() => {
    if (path.startsWith("/login")) return;
    const abort = new AbortController();
    const load = () => {
      fetch(apiUrl(`/users/${USER_ID}`), { signal: abort.signal }).then(async response => {
        if (response.ok) { const user = await response.json(); setUnits(user.units === "km" ? "km" : "miles"); }
      }).catch(() => { /* The page's normal data loader exposes connection errors. */ });
    };
    load();
    window.addEventListener(PREFERENCES_EVENT, load);
    return () => { abort.abort(); window.removeEventListener(PREFERENCES_EVENT, load); };
  }, [path]);
  return <UnitsContext.Provider value={units}>{children}</UnitsContext.Provider>;
}
export const useUnits = () => useContext(UnitsContext);
