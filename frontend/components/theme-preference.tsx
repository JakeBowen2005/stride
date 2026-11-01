"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, USER_ID } from "@/lib/api";
import { DEFAULT_THEME, THEME_KEY, THEME_QUERY as QUERY, type ThemeChoice } from "@/lib/theme";

export type { ThemeChoice } from "@/lib/theme";

const listeners = new Set<() => void>();
let memoryChoice: ThemeChoice = DEFAULT_THEME;
let accountId: number | null = null;
let savingTheme = false;

function isChoice(value: unknown): value is ThemeChoice {
  return value === "light" || value === "dark" || value === "system";
}

/** The profile is authoritative across devices; scoped caches keep accounts separate. */
export function syncUserTheme(user: { id: number; theme?: ThemeChoice | null }) {
  if (savingTheme) return;
  accountId = user.id;
  let choice = user.theme;
  if (!isChoice(choice)) {
    try {
      choice = window.localStorage.getItem(`${THEME_KEY}:${user.id}`) as ThemeChoice;
      const cachedAccount = window.localStorage.getItem(`${THEME_KEY}:account`);
      // Adopt the pre-account browser preference once, then keep caches scoped.
      if (!isChoice(choice) && (cachedAccount === null || cachedAccount === String(user.id))) choice = readChoice();
    } catch { /* cache optional */ }
  }
  writeChoice(isChoice(choice) ? choice : DEFAULT_THEME);
}

function readChoice(): ThemeChoice {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" || value === "system" ? value : DEFAULT_THEME;
  } catch {
    return memoryChoice;
  }
}

function apply(choice: ThemeChoice) {
  const dark = choice === "dark" || (choice === "system" && window.matchMedia(QUERY).matches);
  document.documentElement.classList.toggle("dark", dark);
}

function writeChoice(choice: ThemeChoice) {
  memoryChoice = choice;
  try {
    window.localStorage.setItem(THEME_KEY, choice);
    if (accountId !== null) {
      window.localStorage.setItem(`${THEME_KEY}:${accountId}`, choice);
      window.localStorage.setItem(`${THEME_KEY}:account`, String(accountId));
    }
  } catch {
    // storage unavailable: the choice lasts for this page view
  }
  apply(choice);
  listeners.forEach((l) => l());
}

async function saveChoice(next: ThemeChoice) {
  const previous = readChoice();
  savingTheme = true;
  writeChoice(next);
  try {
    const response = await fetch(apiUrl(`/users/${USER_ID}/profile`), {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ theme: next }),
    });
    if (!response.ok) throw new Error("Could not save appearance. Try again.");
  } catch (error) {
    writeChoice(previous);
    throw error;
  } finally { savingTheme = false; }
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Follows the OS setting live while the athlete's choice is "system". */
export function ThemeWatcher() {
  useEffect(() => {
    const query = window.matchMedia(QUERY);
    const onChange = () => { if (readChoice() === "system") apply("system"); };
    const onStorage = (event: StorageEvent) => {
      if (event.key === THEME_KEY) { apply(readChoice()); listeners.forEach((l) => l()); }
    };
    query.addEventListener("change", onChange);
    window.addEventListener("storage", onStorage);
    return () => { query.removeEventListener("change", onChange); window.removeEventListener("storage", onStorage); };
  }, []);
  return null;
}

const OPTIONS: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Daybreak", icon: Sun },
  { value: "dark", label: "Dusk", icon: Moon },
];

/** System / light / dark switch for Settings: a radiogroup with arrow-key movement. */
export function ThemePreference() {
  const choice = useSyncExternalStore(subscribe, readChoice, () => DEFAULT_THEME);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const choose = async (next: ThemeChoice) => {
    if (savingTheme) return;
    setSaving(true); setStatus("");
    try {
      await saveChoice(next);
      setStatus("Appearance saved to your account");
    } catch {
      setStatus("Could not save appearance. Try again.");
    } finally { setSaving(false); }
  };
  const move = (index: number) => {
    const next = OPTIONS[(index + OPTIONS.length) % OPTIONS.length];
    void choose(next.value);
    refs.current[(index + OPTIONS.length) % OPTIONS.length]?.focus();
  };
  return (
    <div className="space-y-2">
    <div role="radiogroup" aria-label="Theme" aria-busy={saving} className="glass-tile flex w-full gap-1 rounded-full p-1 sm:inline-flex sm:w-auto">
      {OPTIONS.map((option, index) => {
        const active = choice === option.value;
        return (
          <button key={option.value} ref={(el) => { refs.current[index] = el; }} type="button" role="radio" aria-checked={active}
            tabIndex={active ? 0 : -1} disabled={saving} onClick={() => void choose(option.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(index + 1); }
              if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(index - 1); }
            }}
            className={cn("inline-flex min-h-10 flex-1 items-center justify-center gap-1.5 rounded-full px-3 text-sm font-medium transition-colors sm:flex-none sm:px-4",
              active ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-[var(--row-hover)] hover:text-foreground")}>
            <option.icon className="size-4" aria-hidden /> {option.label}
          </button>
        );
      })}
    </div>
    <p role="status" className="min-h-4 text-xs text-muted-foreground">{saving ? "Saving appearance…" : status}</p>
    </div>
  );
}
