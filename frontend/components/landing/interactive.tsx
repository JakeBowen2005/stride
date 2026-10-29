"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check } from "lucide-react";

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const finePointer = () => window.matchMedia("(hover: hover) and (pointer: fine)").matches;

/** Sticky nav that gains its frosted bar once the page scrolls under it. */
export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <header className="lp-nav" data-scrolled={scrolled}>
      <div className="lp-wrap">
        <div className="lp-nav-bar">
          <Link href="/welcome" className="lp-wordmark" aria-label="Stride home">
            <span className="lp-wordmark-dot" aria-hidden />Stride
          </Link>
          <nav className="lp-nav-links" aria-label="Sections">
            <a href="#runners">Who it&apos;s for</a>
            <a href="#paces">Paces</a>
            <a href="#how">How it works</a>
            <a href="#founder">Founder</a>
            <a href="#contact">Contact</a>
          </nav>
          <div className="flex items-center gap-1.5">
            <Link href="/login" className="lp-btn lp-btn-ghost lp-btn-sm">Sign in</Link>
            <Link href="/auth/register" className="lp-btn lp-btn-primary lp-btn-sm">Create account</Link>
          </div>
        </div>
      </div>
    </header>
  );
}

/** Today's workout card. Tilts toward the pointer on a soft follow (decorative; fine pointers only). */
export function TiltCard({ children }: { children: ReactNode }) {
  const stage = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = stage.current, inner = card.current;
    if (!el || !inner || !finePointer() || reducedMotion()) return;
    const target = { x: 0, y: 0 }, cur = { x: 0, y: 0 };
    let raf = 0;
    const tick = () => {
      // Critically damped follow: eases toward the pointer without overshoot.
      cur.x += (target.x - cur.x) * 0.12;
      cur.y += (target.y - cur.y) * 0.12;
      inner.style.transform = `rotateX(${cur.y * -7}deg) rotateY(${cur.x * 9}deg) translateZ(0)`;
      if (Math.abs(target.x - cur.x) > 0.001 || Math.abs(target.y - cur.y) > 0.001) raf = requestAnimationFrame(tick);
      else raf = 0;
    };
    const kick = () => { if (!raf) raf = requestAnimationFrame(tick); };
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
      target.x = px - 0.5; target.y = py - 0.5;
      inner.style.setProperty("--gx", `${px * 100}%`);
      inner.style.setProperty("--gy", `${py * 100}%`);
      kick();
    };
    const enter = () => { el.dataset.active = "true"; };
    const leave = () => { el.dataset.active = "false"; target.x = 0; target.y = 0; kick(); };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerenter", enter);
    el.addEventListener("pointerleave", leave);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerenter", enter);
      el.removeEventListener("pointerleave", leave);
    };
  }, []);
  return (
    <div ref={stage} className="lp-card-stage">
      <div ref={card} className="lp-glass lp-today">
        <div className="lp-today-glare" aria-hidden />
        {children}
      </div>
    </div>
  );
}

/** Sets data-visible once the element scrolls into view, for one-shot reveals. */
export function Reveal({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setVisible(true); io.disconnect(); }
    }, { rootMargin: "0px 0px -100px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return <div ref={ref} className={className} data-visible={visible}>{children}</div>;
}

type Kind = "easy" | "hard" | "long" | "rest";
type Day = { d: string; mi: number; kind: Kind; label: string };
type Profile = { key: string; tab: string; title: string; blurb: string; miles: number; days: Day[]; points: string[] };

const PROFILES: Profile[] = [
  {
    key: "new", tab: "First 5K",
    title: "Start running. Keep running.",
    blurb: "Four days a week, every one of them easy enough to talk through. We grow the week slowly, because the goal is still running in six months.",
    miles: 14,
    days: [
      { d: "Mon", mi: 0, kind: "rest", label: "Rest" },
      { d: "Tue", mi: 3, kind: "easy", label: "Easy" },
      { d: "Wed", mi: 0, kind: "rest", label: "Rest" },
      { d: "Thu", mi: 3, kind: "easy", label: "Easy + strides" },
      { d: "Fri", mi: 0, kind: "rest", label: "Rest" },
      { d: "Sat", mi: 5, kind: "long", label: "Long" },
      { d: "Sun", mi: 3, kind: "easy", label: "Easy" },
    ],
    points: ["Weekly mileage grows by 10% at most, strictly", "Easy means conversational: we'll tell you to slow down", "A lighter week every fourth week so your legs catch up"],
  },
  {
    key: "pr", tab: "Chasing a PR",
    title: "Two real sessions. Everything else easy.",
    blurb: "Intervals early in the week, threshold later, a long run on the weekend. Paces come from your goal time and adjust to your actual splits.",
    miles: 46,
    days: [
      { d: "Mon", mi: 6, kind: "easy", label: "Easy" },
      { d: "Tue", mi: 8, kind: "hard", label: "6×800m" },
      { d: "Wed", mi: 6, kind: "easy", label: "Easy" },
      { d: "Thu", mi: 9, kind: "hard", label: "4×10 min" },
      { d: "Fri", mi: 0, kind: "rest", label: "Rest" },
      { d: "Sat", mi: 12, kind: "long", label: "Long" },
      { d: "Sun", mi: 5, kind: "easy", label: "Easy" },
    ],
    points: ["Never two hard days back to back", "Miss your splits and the next session holds instead of progressing", "Rolling two-week blocks you approve before they start"],
  },
  {
    key: "elite", tab: "High mileage",
    title: "Built for the 80-mile week.",
    blurb: "Doubles, marathon-pace long runs and longer cycles between down weeks, but only once your history shows you can absorb them.",
    miles: 82,
    days: [
      { d: "Mon", mi: 14, kind: "easy", label: "Easy + PM double" },
      { d: "Tue", mi: 12, kind: "hard", label: "5×1K" },
      { d: "Wed", mi: 10, kind: "easy", label: "Easy" },
      { d: "Thu", mi: 13, kind: "hard", label: "2×20 min" },
      { d: "Fri", mi: 7, kind: "easy", label: "Recovery" },
      { d: "Sat", mi: 18, kind: "long", label: "Last 5 @ MP" },
      { d: "Sun", mi: 8, kind: "easy", label: "Easy" },
    ],
    points: ["Down weeks every 7th or 8th week instead of every 4th", "Acute:chronic load watched every day, not every block", "Ultra blocks with time-on-feet long runs and fueling targets"],
  },
];
const MAX_DAY = 18;

/** Three runners, one engine: a segmented switch swaps the sample week. */
export function RunnerProfiles() {
  const [active, setActive] = useState(0);
  const [shown, setShown] = useState(0);
  const [swapping, setSwapping] = useState(false);
  const timer = useRef<number>(0);
  const n = PROFILES.length;

  const choose = (i: number) => {
    setActive(i);
    window.clearTimeout(timer.current);
    if (reducedMotion()) { setShown(i); return; }
    setSwapping(true);
    timer.current = window.setTimeout(() => { setShown(i); setSwapping(false); }, 180);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const p = PROFILES[shown];
  // Bars follow the active tab immediately; only the text waits for the blur seam.
  const bars = PROFILES[active].days;
  const clip = `inset(0 ${((n - 1 - active) / n) * 100}% 0 ${(active / n) * 100}% round 999px)`;

  return (
    <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:gap-14">
      <div>
        <div className="lp-seg" role="tablist" aria-label="Runner type">
          {PROFILES.map((pr, i) => (
            <button key={pr.key} role="tab" aria-selected={active === i} aria-controls="lp-profile" onClick={() => choose(i)}>{pr.tab}</button>
          ))}
          <div className="lp-seg-active" style={{ clipPath: clip }} aria-hidden>
            {PROFILES.map((pr) => <span key={pr.key}>{pr.tab}</span>)}
          </div>
        </div>

        <div id="lp-profile" role="tabpanel" className="lp-swap mt-8" data-swapping={swapping}>
          <h3 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.03em] sm:text-[2rem]">{p.title}</h3>
          <p className="lp-lede mt-3">{p.blurb}</p>
          <ul className="mt-7 space-y-4">
            {p.points.map((pt) => (
              <li key={pt} className="lp-check text-[15px] leading-snug">
                <span className="lp-check-mark"><Check size={13} strokeWidth={2.6} /></span>{pt}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="lp-glass p-5 sm:p-7">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.14em] text-[var(--lp-faint)]">Sample week</div>
            <div className="lp-swap mt-1 text-sm text-[var(--lp-muted)]" data-swapping={swapping}>{p.tab}</div>
          </div>
          <div className="text-right">
            <div className="lp-mono lp-swap text-4xl font-medium leading-none sm:text-5xl" data-swapping={swapping}>{p.miles}</div>
            <div className="mt-1 text-xs text-[var(--lp-faint)]">miles</div>
          </div>
        </div>
        <div className="lp-week">
          {bars.map((day, i) => (
            <div key={day.d} className="lp-day">
              <div className="lp-day-col">
                <div className="lp-day-fill" data-kind={day.kind} style={{ transform: `scaleY(${day.mi ? Math.max(day.mi / MAX_DAY, 0.12) : 0})`, transitionDelay: `${i * 30}ms` }} />
                <div className="lp-day-miles lp-mono">{day.mi || "–"}</div>
              </div>
              <div className="text-center">
                <div className="text-[11px] font-semibold text-[var(--lp-muted)]">{day.d}</div>
                <div className="lp-swap mt-0.5 truncate text-[10.5px] text-[var(--lp-faint)] sm:text-[11.5px]" data-swapping={swapping} title={PROFILES[shown].days[i].label}>{PROFILES[shown].days[i].label}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--lp-faint)]">
          <span className="inline-flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-[#96afe6]" />Easy</span>
          <span className="inline-flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-[var(--lp-peach)]" />Workout</span>
          <span className="inline-flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-[#c9909e]" />Long run</span>
        </div>
      </div>
    </div>
  );
}

// The plan engine's 5K multipliers (backend/app/core/pacing.py goal_paces, distance "5k").
const MI_5K = 3.10686;
const KM_PER_MI = 1.609344;
const fmt = (s: number) => {
  const r = Math.round(s);
  return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`;
};

/** Drag a 5K goal; every training pace follows. */
export function PaceLab() {
  const [goal, setGoal] = useState(22 * 60);
  const [unit, setUnit] = useState<"mi" | "km">("mi");
  const min = 14 * 60, max = 40 * 60;
  const race = goal / MI_5K; // seconds per mile
  const per = (secPerMile: number) => (unit === "mi" ? secPerMile : secPerMile / KM_PER_MI);
  const interval = race * 0.95;
  const rep800 = interval * (800 / 1609.344);
  const rows = [
    { name: "Intervals", note: `6×800m in ${fmt(rep800)}`, pace: fmt(per(interval)) },
    { name: "5K race pace", note: "Goal pace", pace: fmt(per(race)) },
    { name: "Tempo", note: "Comfortably hard", pace: fmt(per(race * 1.08)) },
    { name: "Long run", note: "Steady, relaxed", pace: fmt(per(race * 1.55)) },
    { name: "Easy", note: "Conversational", pace: `${fmt(per(race * 1.5))}–${fmt(per(race * 1.7))}` },
  ];
  const fill = `${((goal - min) / (max - min)) * 100}%`;

  return (
    <div className="lp-glass grid gap-8 p-5 sm:p-8 lg:grid-cols-[1fr_1.1fr] lg:gap-12">
      <div className="flex flex-col">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor="lp-goal" className="text-xs uppercase tracking-[0.14em] text-[var(--lp-faint)]">Your 5K goal</label>
          <div className="lp-unit" role="group" aria-label="Units">
            <button aria-pressed={unit === "mi"} onClick={() => setUnit("mi")}>mi</button>
            <button aria-pressed={unit === "km"} onClick={() => setUnit("km")}>km</button>
          </div>
        </div>
        <output htmlFor="lp-goal" className="lp-mono mt-4 block text-[clamp(4rem,12vw,6.5rem)] font-medium leading-none tracking-[-0.04em]">{fmt(goal)}</output>
        <input id="lp-goal" className="lp-range mt-6" type="range" min={min} max={max} step={5} value={goal}
          style={{ ["--fill" as string]: fill }} onChange={(e) => setGoal(Number(e.target.value))}
          aria-valuetext={`${Math.floor(goal / 60)} minutes ${goal % 60} seconds`} />
        <div className="lp-mono flex justify-between text-xs text-[var(--lp-faint)]"><span>14:00</span><span>40:00</span></div>
        <p className="mt-auto pt-8 text-sm leading-relaxed text-[var(--lp-muted)]">
          These are the same multipliers Stride&apos;s plan engine uses. Once your runs sync, paces recalibrate from what your splits
          actually say you can do.
        </p>
      </div>
      <div aria-live="polite">
        {rows.map((r) => (
          <div key={r.name} className="lp-pace-row">
            <div>
              <div className="font-semibold">{r.name}</div>
              <div className="text-sm text-[var(--lp-faint)]">{r.note}</div>
            </div>
            <div className="lp-mono text-right text-2xl font-medium sm:text-[1.75rem]">
              {r.pace}<span className="ml-1 text-sm text-[var(--lp-faint)]">/{unit}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
