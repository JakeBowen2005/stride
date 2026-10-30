"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { CalendarDays, History, LogOut, Settings, Sun } from "lucide-react";
import { GarminSync } from "@/components/garmin-sync";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Today", icon: Sun },
  { href: "/plan", label: "Plan", icon: CalendarDays },
  { href: "/history", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

const isActive = (pathname: string, href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
// Sign-in and public pages (privacy policy, about) show only the wordmark: no app nav or Garmin status.
const isAuthPage = (pathname: string) => pathname.startsWith("/login") || pathname.startsWith("/auth")
  || pathname === "/privacy" || pathname === "/about";

function Wordmark({ className }: { className?: string }) {
  return <Link href="/" className={cn("wordmark rounded-full text-[21px] leading-none", className)}>Stride</Link>;
}

/** The bar gains a stronger frosted background once the page scrolls under it. */
function useScrolled() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return scrolled;
}

/** One sticky top bar: wordmark, a centered pill switcher (tablets and up), Garmin status and sign out. */
export function Nav() {
  const pathname = usePathname();
  const scrolled = useScrolled();
  if (isAuthPage(pathname)) return <header className="px-4 pt-5 sm:px-0"><Wordmark /></header>;
  return (
    <header className={cn("sticky top-0 z-50 -mx-0 transition-[padding] duration-200 sm:top-3 sm:pt-4", scrolled && "sm:pt-0")}>
      <div className={cn("flex h-14 items-center justify-between gap-3 px-4 transition-all duration-200 sm:h-16 sm:rounded-full sm:border sm:px-3 sm:pl-5",
        scrolled ? "glass-strong border-b shadow-[var(--glass-shadow)] sm:border-[var(--glass-border)]" : "border-transparent bg-transparent")}>
        <Wordmark className="shrink-0" />
        <nav className="glass-tile hidden items-center gap-1 rounded-full p-1 sm:flex" aria-label="Main">
          {links.map((link) => {
            const active = isActive(pathname, link.href);
            return (
              <Link key={link.href} href={link.href} aria-current={active ? "page" : undefined}
                className={cn("rounded-full px-4 py-2 text-[13px] transition-[color,background-color] duration-150 lg:px-6",
                  active ? "btn-gloss font-semibold" : "font-medium text-muted-foreground hover:bg-[var(--row-hover)] hover:text-foreground")}>
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="flex min-w-0 items-center justify-end gap-1 sm:w-[clamp(9rem,22vw,17rem)]">
          <GarminSync variant="bar" />
          <form action="/auth/logout" method="post" className="max-sm:hidden">
            <button type="submit" aria-label="Sign out" title="Sign out"
              className="grid size-9 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-[var(--row-hover)] hover:text-foreground">
              <LogOut className="size-4" aria-hidden />
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}

/** Phones: a floating glass tab bar above the home indicator. */
export function MobileNav() {
  const pathname = usePathname();
  if (isAuthPage(pathname)) return null;
  return (
    <nav className="fixed inset-x-3 bottom-[calc(.75rem+env(safe-area-inset-bottom))] z-50 sm:hidden" aria-label="Main">
      <div className="glass-strong flex h-16 items-stretch gap-1 rounded-full p-1.5 shadow-[var(--glass-shadow)]">
        {links.map((link) => {
          const active = isActive(pathname, link.href);
          return (
            <Link key={link.href} href={link.href} aria-current={active ? "page" : undefined}
              className={cn("flex flex-1 flex-col items-center justify-center gap-0.5 rounded-full text-[11px] font-semibold transition-colors focus-visible:outline-offset-[-3px]",
                active ? "btn-gloss" : "text-muted-foreground hover:text-foreground")}>
              <link.icon className="size-5" aria-hidden="true" />
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
