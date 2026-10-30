"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";

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
            <a href="#how">How it works</a>
            <a href="#paces">Paces</a>
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
    key: "new", tab: "New runner",
    title: "Start running. Keep running.",
    blurb: "Four days a week, every one easy enough to talk through, building toward a first 5K or simply running consistently. The goal is still running in six months.",
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
    key: "pr", tab: "Racing a PR",
    title: "Two real sessions. Everything else easy.",
    blurb: "Whether it's a 5K, 10K or half marathon: speed early in the week, threshold later, a long run on the weekend. Paces come from your goal and recalibrate from your splits.",
    miles: 50,
    days: [
      { d: "Mon", mi: 6, kind: "easy", label: "Easy" },
      { d: "Tue", mi: 9, kind: "hard", label: "5×1 mi" },
      { d: "Wed", mi: 6, kind: "easy", label: "Easy" },
      { d: "Thu", mi: 10, kind: "hard", label: "3×15 min" },
      { d: "Fri", mi: 0, kind: "rest", label: "Rest" },
      { d: "Sat", mi: 14, kind: "long", label: "Progression" },
      { d: "Sun", mi: 5, kind: "easy", label: "Easy" },
    ],
    points: ["Never two hard days back to back", "Miss your splits and the next session holds instead of progressing", "Peak, taper and race week counted back from race day"],
  },
  {
    key: "marathon", tab: "Marathon",
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
    points: ["Down weeks every 7th or 8th week instead of every 4th", "Doubles only when your training history earns them", "Acute:chronic load watched every day, not every block"],
  },
  {
    key: "ultra", tab: "Ultra",
    title: "Time on feet, from 50K to 100 miles.",
    blurb: "Long runs measured in hours with fueling targets, back-to-back weekends, and hills instead of the track when the race is on trail.",
    miles: 65,
    days: [
      { d: "Mon", mi: 0, kind: "rest", label: "Rest" },
      { d: "Tue", mi: 9, kind: "hard", label: "Hill repeats" },
      { d: "Wed", mi: 8, kind: "easy", label: "Easy" },
      { d: "Thu", mi: 10, kind: "hard", label: "Tempo" },
      { d: "Fri", mi: 6, kind: "easy", label: "Easy" },
      { d: "Sat", mi: 20, kind: "long", label: "4 hr trail" },
      { d: "Sun", mi: 12, kind: "long", label: "2 hr B2B" },
    ],
    points: ["Back-to-back long runs every other build week", "Fueling targets on every long run", "A readiness check suggests a stepping-stone race if you need one"],
  },
];
const MAX_DAY = 20;

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

type Bar = { v: number; label?: string; kind?: "work" | "easy" | "fuel" };
type Workout = {
  goal: string; day: string; phase: string; volume: string;
  title: string; detail: string; chart: string; target?: string;
  bars: Bar[]; why: string; feel: string; next: string;
};

// One session per goal. Bar values are 0–1 heights; labels sit under the bars.
const WORKOUTS: Workout[] = [
  {
    goal: "5K", day: "Tuesday · Intervals", phase: "Build · week 6", volume: "7.2 mi",
    title: "6 × 800m", detail: "at 5K goal pace · 90s jog · 1 mi warm-up, 1 mi cool-down",
    chart: "Your reps", target: "on target",
    bars: [0.66, 0.6, 0.72, 0.54, 0.66, 0.8].map((v, i) => ({ v, label: ["3:20", "3:21", "3:19", "3:22", "3:20", "3:18"][i], kind: "work" })),
    why: "VO₂max work a touch faster than goal pace, so race pace starts to feel like cruising.",
    feel: "Strong · RPE 7", next: "Thursday threshold holds",
  },
  {
    goal: "Half marathon", day: "Thursday · Threshold", phase: "Build · week 4", volume: "9 mi",
    title: "4 × 10 min", detail: "at threshold · 2 min jog · 2 mi warm-up, 1 mi cool-down",
    chart: "Each rep", target: "comfortably hard",
    bars: [0.62, 0.66, 0.68, 0.72].map((v, i) => ({ v, label: `Rep ${i + 1}`, kind: "work" })),
    why: "Raises lactate threshold, the pace you can hold for an hour and the key limiter for the half.",
    feel: "Good · RPE 6", next: "Saturday long run progresses",
  },
  {
    goal: "Marathon", day: "Saturday · Long run", phase: "Peak · week 11", volume: "18 mi",
    title: "18 mi", detail: "13 easy, last 5 at marathon pace · fuel every 45 min",
    chart: "Mile by mile", target: "finish at goal pace",
    bars: Array.from({ length: 18 }, (_, i) => ({ v: i < 13 ? 0.38 + (i % 3) * 0.02 : 0.78, label: i === 0 || i === 12 || i === 17 ? String(i + 1) : undefined, kind: i < 13 ? "easy" as const : "work" as const })),
    why: "Race-specific endurance: practising goal pace on tired legs, the way the last 10K will feel.",
    feel: "Strong · RPE 7", next: "Monday stays easy",
  },
  {
    goal: "100K", day: "Saturday · Back-to-back", phase: "Build · week 9", volume: "4 hr",
    title: "4 hr trail", detail: "time on feet, not pace · 2 hr easy tomorrow on tired legs",
    chart: "Carbs per hour", target: "60–90 g",
    bars: [0.7, 0.78, 0.82, 0.8].map((v, i) => ({ v, label: `Hr ${i + 1}`, kind: "fuel" })),
    why: "Teaches your legs and your gut to keep working hours into the day, with a fueling target to practise.",
    feel: "Steady · RPE 5", next: "Sunday 2 hr confirmed",
  },
  {
    goal: "First 5K", day: "Wednesday · Easy", phase: "Week 3", volume: "3 mi",
    title: "3 mi easy", detail: "conversational effort · 4 × 20s strides to finish",
    chart: "Effort", target: "talk the whole way",
    bars: [0.34, 0.36, 0.35, 0.86, 0.86, 0.86, 0.86].map((v, i) => ({ v, label: i < 3 ? `Mi ${i + 1}` : i === 3 ? "Strides" : undefined, kind: i < 3 ? "easy" : "work" })),
    why: "Builds the aerobic base everything else sits on. Strides keep your stride quick without any strain.",
    feel: "Easy · RPE 3", next: "Saturday long run on track",
  },
];

/** Hero card: today's session for different goals. Arrows, dots or a swipe move between them. */
export function WorkoutCarousel() {
  const [index, setIndex] = useState(0);
  const [dir, setDir] = useState(1);
  const [ready, setReady] = useState(false);
  const drag = useRef<{ x: number; y: number; t: number; id: number } | null>(null);
  const n = WORKOUTS.length;
  // One frame after mount, so the first slide's bars rise from their resting height.
  useEffect(() => {
    const raf = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  const go = (step: number) => { setDir(step); setIndex((i) => (i + step + n) % n); };
  const jump = (i: number) => { setDir(i > index ? 1 : -1); setIndex(i); };

  // Swipe: a short flick counts as much as a long drag (velocity, not only distance).
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.pointerType === "mouse" || drag.current) return;
    drag.current = { x: e.clientX, y: e.clientY, t: Date.now(), id: e.pointerId };
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (Math.abs(dx) < Math.abs(dy)) return;
    const velocity = Math.abs(dx) / Math.max(Date.now() - d.t, 1);
    if (Math.abs(dx) > 50 || velocity > 0.11) go(dx < 0 ? 1 : -1);
  };

  return (
    <div onPointerDown={onPointerDown} onPointerUp={onPointerUp} onPointerCancel={() => { drag.current = null; }}
      className="lp-carousel" role="region" aria-roledescription="carousel" aria-label="Sample workouts by goal">
      <div className="lp-slides">
        {WORKOUTS.map((w, i) => {
          const active = i === index;
          const offset = active ? 0 : (i < index ? -1 : 1) * dir;
          return (
            <div key={w.goal} className="lp-slide" data-active={ready && active} aria-hidden={!active}
              style={{ ["--from" as string]: `${offset * 18}px` }} role="group" aria-roledescription="slide" aria-label={`${w.goal}: ${w.title}`}>
              <div className="flex items-center justify-between gap-3">
                <div className="flex flex-wrap gap-2">
                  <span className="lp-chip lp-chip-warm">{w.day}</span>
                  <span className="lp-chip">{w.phase}</span>
                </div>
                <span className="lp-mono shrink-0 text-xs text-[var(--lp-faint)]">{w.volume}</span>
              </div>
              <div className="mt-6">
                <div className="text-xs uppercase tracking-[0.14em] text-[var(--lp-apricot)]">{w.goal} goal</div>
                <div className="lp-mono mt-2 text-[clamp(2.3rem,6vw,3.1rem)] font-medium leading-none tracking-[-0.04em]">{w.title}</div>
                <div className="mt-2 text-[15px] text-[var(--lp-muted)]">{w.detail}</div>
              </div>
              <div className="mt-7">
                <div className="mb-2 flex justify-between text-[11px] uppercase tracking-[0.12em] text-[var(--lp-faint)]">
                  <span>{w.chart}</span>{w.target && <span>{w.target}</span>}
                </div>
                <div className="lp-reps" style={{ gridTemplateColumns: `repeat(${w.bars.length}, 1fr)`, gap: w.bars.length > 10 ? 4 : 8 }}>
                  {w.bars.map((b, j) => (
                    <div key={j} className="lp-rep">
                      <div className="lp-rep-bar" data-kind={b.kind} style={{ ["--i" as string]: j, height: `${b.v * 100}%` }} />
                    </div>
                  ))}
                </div>
                <div className="mt-2 grid" style={{ gridTemplateColumns: `repeat(${w.bars.length}, 1fr)`, gap: w.bars.length > 10 ? 4 : 8 }}>
                  {w.bars.map((b, j) => (
                    <span key={j} className="lp-mono overflow-visible whitespace-nowrap text-center text-[11.5px] text-[var(--lp-muted)]">{b.label ?? ""}</span>
                  ))}
                </div>
              </div>
              <div className="mt-6 rounded-2xl bg-[rgba(255,255,255,0.05)] p-4 text-sm leading-relaxed text-[var(--lp-muted)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.07)]">
                <span className="lp-serif text-[17px] italic text-[var(--lp-cream)]">Why: </span>{w.why}
              </div>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-[13px]">
                <span className="text-[var(--lp-muted)]">Watch feel: <b className="font-semibold text-[var(--lp-text)]">{w.feel}</b></span>
                <span className="inline-flex items-center gap-2 text-[#9be7bd]"><span className="h-1.5 w-1.5 rounded-full bg-current" />{w.next}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 flex items-center justify-between gap-4 border-t border-[var(--lp-line)] pt-5">
        <div className="flex items-center gap-1.5" role="tablist" aria-label="Choose a goal">
          {WORKOUTS.map((w, i) => (
            <button key={w.goal} role="tab" aria-selected={i === index} aria-label={w.goal} onClick={() => jump(i)} className="lp-dot" data-active={i === index} />
          ))}
          <span className="ml-2 text-xs text-[var(--lp-faint)]">{WORKOUTS[index].goal}</span>
        </div>
        <div className="flex gap-2">
          <button className="lp-arrow" onClick={() => go(-1)} aria-label="Previous workout"><ChevronLeft size={18} /></button>
          <button className="lp-arrow" onClick={() => go(1)} aria-label="Next workout"><ChevronRight size={18} /></button>
        </div>
      </div>
    </div>
  );
}
