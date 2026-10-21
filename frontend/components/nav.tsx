"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarDays, History, Settings, Sun, Zap } from "lucide-react";
import { GarminSync } from "@/components/garmin-sync";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Today", icon: Sun },
  { href: "/plan", label: "Plan", icon: CalendarDays },
  { href: "/history", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

const isActive = (pathname: string, href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

function Wordmark({ className }: { className?: string }) {
  return (
    <Link href="/" className={cn("flex items-center gap-1.5 font-heading text-lg font-black italic tracking-tight", className)}>
      <Zap className="size-4 fill-[#34d399] text-[#34d399]" aria-hidden="true" /> STRIDE
    </Link>
  );
}

/** Desktop: fixed dark sidebar. Below 1024px: dark top bar (+ bottom tabs on phones). */
export function Nav() {
  const pathname = usePathname();
  if (pathname.startsWith("/login")) return <header className="bg-[var(--ink)] px-4 py-3 text-white"><Wordmark /></header>;
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-50 hidden w-[184px] flex-col bg-[var(--ink)] px-3 py-4 text-white lg:flex">
        <Wordmark className="px-2 text-white" />
        <nav className="mt-6 space-y-1" aria-label="Main">
          {links.map((link) => {
            const active = isActive(pathname, link.href);
            return (
              <Link key={link.href} href={link.href} aria-current={active ? "page" : undefined}
                className={cn("flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-[#34d399]",
                  active ? "bg-white text-[#1f1f1f]" : "text-[#d4d4cf] hover:bg-white/10 hover:text-white")}>
                <link.icon className="size-4" aria-hidden="true" /> {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto border-t border-white/10 px-2 pt-3">
          <GarminSync variant="sidebar" autoSync={false} />
          <form action="/auth/logout" method="post" className="mt-3"><button className="min-h-9 text-xs text-[#d4d4cf] underline underline-offset-2">Sign out</button></form>
        </div>
      </aside>
      <header className="sticky top-0 z-50 bg-[var(--ink)] text-white lg:hidden">
        <div className="flex h-12 items-center justify-between px-4">
          <Wordmark className="text-white" />
          <nav className="hidden items-center gap-1 sm:flex" aria-label="Main">
            {links.map((link) => {
              const active = isActive(pathname, link.href);
              return (
                <Link key={link.href} href={link.href} aria-current={active ? "page" : undefined}
                  className={cn("rounded-md px-3 py-1 text-sm font-medium focus-visible:outline-2 focus-visible:outline-[#34d399]", active ? "bg-white text-[#1f1f1f]" : "text-[#d4d4cf] hover:text-white")}>
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
    </>
  );
}

export function MobileNav() {
  const pathname = usePathname();
  if (pathname.startsWith("/login")) return null;
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-[var(--ink)] pb-[env(safe-area-inset-bottom)] sm:hidden" aria-label="Main">
      <div className="flex h-14 items-stretch">
        {links.map((link) => {
          const active = isActive(pathname, link.href);
          return (
            <Link key={link.href} href={link.href} aria-current={active ? "page" : undefined}
              className={cn("flex flex-1 flex-col items-center justify-center gap-0.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#34d399]",
                active ? "text-white" : "text-[#a8a8a2]")}>
              <link.icon className="size-5" aria-hidden="true" />
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
