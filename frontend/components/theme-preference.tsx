"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

export type ThemeChoice = "system" | "light" | "dark";
export const THEME_KEY = "stride-theme";
const QUERY = "(prefers-color-scheme: dark)";
/** Dusk until the athlete picks otherwise: the app shares the landing page's look. */
const DEFAULT_THEME: ThemeChoice = "dark";

/** Runs in <head> before paint so the page never flashes the wrong theme. */
export const THEME_BOOT_SCRIPT = `(function(){var d=false;try{var t=localStorage.getItem("${THEME_KEY}")||"${DEFAULT_THEME}";d=t==="dark"||(t!=="light"&&matchMedia("${QUERY}").matches);}catch(e){d=true;}document.documentElement.classList.toggle("dark",d);})()`;

const listeners = new Set<() => void>();
let memoryChoice: ThemeChoice = DEFAULT_THEME;

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
  } catch {
    // storage unavailable: the choice lasts for this page view
  }
  apply(choice);
  listeners.forEach((l) => l());
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
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
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
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (index: number) => {
    const next = OPTIONS[(index + OPTIONS.length) % OPTIONS.length];
    writeChoice(next.value);
    refs.current[(index + OPTIONS.length) % OPTIONS.length]?.focus();
  };
  return (
    <div role="radiogroup" aria-label="Theme" className="glass-tile flex w-full gap-1 rounded-full p-1 sm:inline-flex sm:w-auto">
      {OPTIONS.map((option, index) => {
        const active = choice === option.value;
        return (
          <button key={option.value} ref={(el) => { refs.current[index] = el; }} type="button" role="radio" aria-checked={active}
            tabIndex={active ? 0 : -1} onClick={() => writeChoice(option.value)}
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
  );
}
