import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Mail, MapPin } from "lucide-react";
import { LandingNav, PaceLab, Reveal, RunnerProfiles, TiltCard } from "@/components/landing/interactive";
import { CONTACT, LEGAL } from "@/lib/legal";
import "./landing.css";

export const metadata: Metadata = {
  title: "Stride · A running coach that adapts to what you actually ran",
  description:
    "Stride writes two weeks of real training at a time, reads every run from your Garmin, and adjusts what comes next. For first-time runners and high-mileage athletes.",
};

const SESSIONS = [
  ["6×800m", "at 5K pace, 90s jog"],
  ["4×10 min", "threshold, 2 min jog"],
  ["18 mi long run", "last 5 at marathon pace"],
  ["8×200m", "strides on an easy day"],
  ["3 mi", "easy, truly conversational"],
  ["5×1K", "at 3K–5K pace, 2 min jog"],
  ["2×20 min", "cruise tempo"],
  ["10×90s hills", "jog down recovery"],
  ["14 mi progression", "easy to steady to tempo"],
];

// Today card in the hero: a goal of 22:00 for 5K gives 3:21 per 800m at the engine's interval multiplier.
const SPLITS = [200, 201, 199, 202, 200, 198];
const TARGET = 201;
// Faster reps stand taller: 3:14 fills the column, 3:30 is a stub.
const barHeight = (sec: number) => ((214 - sec) / 16) * 62 + 24;

const STEPS = [
  { n: "01", t: "Sync", d: "Runs come in from Garmin Connect with their laps, so every rep is measured, not guessed." },
  { n: "02", t: "Run", d: "Each day tells you what to run, at what pace, the warm-up and cool-down, and why it's there." },
  { n: "03", t: "Tell us how it went", d: "One comment after the run. Your watch's own feel and effort rating does the rest." },
  { n: "04", t: "Adjust", d: "Fixed training rules decide whether the next hard day holds, progresses or eases off. The AI only explains." },
];

const GUARDS = [
  { k: "10%", t: "Ramp ceiling", d: "New runners never add more than a tenth to their week." },
  { k: "0", t: "Back-to-back hard days", d: "There's always an easy day or rest between workouts and long runs." },
  { k: "4–8", t: "Weeks between down weeks", d: "Shorter cycles for newer runners, longer for experienced ones." },
  { k: "HRV", t: "Recovery flags", d: "Poor sleep and a low HRV trend suggest an extra easy day." },
];

export default function Welcome() {
  return (
    <div className="lp">
      <div className="lp-sky" aria-hidden>
        <div className="lp-dusk">
          <div className="lp-sun" />
          <div className="lp-ground" />
          <div className="lp-horizon" />
        </div>
        <div className="lp-grain" />
      </div>

      <LandingNav />

      <main>
        {/* Hero */}
        <section className="lp-hero">
          <div className="lp-wrap lp-hero-grid">
            <div>
              <div className="lp-enter" style={{ ["--i" as string]: 0 }}>
                <span className="lp-pill"><span className="lp-pill-dot" />Free beta, now inviting Garmin runners</span>
              </div>
              <h1 className="lp-h1 mt-7">
                <span className="lp-h1-line lp-enter" style={{ ["--i" as string]: 1 }}>Easy days easy.</span>
                <span className="lp-h1-line lp-enter" style={{ ["--i" as string]: 2 }}>Hard days hard.</span>
                <span className="lp-h1-line lp-enter lp-serif" style={{ ["--i" as string]: 3 }}>Every day explained.</span>
              </h1>
              <p className="lp-lede lp-enter mt-7 text-[1.125rem]" style={{ ["--i" as string]: 4 }}>
                Stride is a running coach that writes two weeks of training at a time, with real sessions like
                <span className="text-[var(--lp-text)]"> 6×800m at 3:21 with a 90-second jog</span>, then reads every run from your watch
                and adjusts what comes next.
              </p>
              <div className="lp-enter mt-9 flex flex-wrap gap-3" style={{ ["--i" as string]: 5 }}>
                <Link href="/auth/register" className="lp-btn lp-btn-primary">Create your account <ArrowRight size={16} /></Link>
                <Link href="/login" className="lp-btn lp-btn-ghost">Sign in</Link>
              </div>
              <p className="lp-enter mt-5 text-sm text-[var(--lp-muted)]" style={{ ["--i" as string]: 6 }}>
                Running only. No cycling, no gym, no fluff.
              </p>
            </div>

            <div className="lp-enter" style={{ ["--i" as string]: 3 }}>
              <TiltCard>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex flex-wrap gap-2">
                    <span className="lp-chip lp-chip-warm">Tuesday · Intervals</span>
                    <span className="lp-chip">Build · week 6</span>
                  </div>
                  <span className="lp-mono text-xs text-[var(--lp-faint)]">7.2 mi</span>
                </div>
                <div className="mt-6">
                  <div className="lp-mono text-[clamp(2.4rem,6vw,3.25rem)] font-medium leading-none tracking-[-0.04em]">6 × 800m</div>
                  <div className="mt-2 text-[15px] text-[var(--lp-muted)]">at <span className="lp-mono text-[var(--lp-text)]">3:21</span> · 90s jog · 1 mi warm-up, 1 mi cool-down</div>
                </div>
                <div className="relative mt-7">
                  <div className="mb-2 flex justify-between text-[11px] uppercase tracking-[0.12em] text-[var(--lp-faint)]">
                    <span>Your reps</span><span>target 3:21</span>
                  </div>
                  <div>
                    <div className="lp-reps relative">
                      <div className="lp-target-line" style={{ bottom: `${barHeight(TARGET)}%` }} aria-hidden />
                      {SPLITS.map((s, i) => (
                        <div key={i} className="lp-rep">
                          <div className="lp-rep-bar" style={{ ["--i" as string]: i, height: `${barHeight(s)}%` }} />
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 grid grid-cols-6 gap-2">
                      {SPLITS.map((s, i) => (
                        <span key={i} className="lp-mono text-center text-[11.5px] text-[var(--lp-muted)]">{`${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`}</span>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="mt-6 rounded-2xl bg-[rgba(255,255,255,0.05)] p-4 text-sm leading-relaxed text-[var(--lp-muted)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.07)]">
                  <span className="lp-serif text-[17px] italic text-[var(--lp-cream)]">Why: </span>
                  VO₂max work a touch faster than goal pace, so 22:00 starts to feel like cruising.
                </div>
                <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-[13px]">
                  <span className="text-[var(--lp-muted)]">Watch feel: <b className="font-semibold text-[var(--lp-text)]">Strong · RPE 7</b></span>
                  <span className="inline-flex items-center gap-2 text-[#9be7bd]"><span className="h-1.5 w-1.5 rounded-full bg-current" />Thursday threshold holds</span>
                </div>
              </TiltCard>
            </div>
          </div>
        </section>

        {/* Real sessions */}
        <div className="lp-marquee" aria-label="Examples of Stride workouts">
          <div className="lp-marquee-track">
            {[0, 1].map((copy) => (
              <div key={copy} className={copy ? "lp-marquee-item lp-marquee-dup" : "lp-marquee-item"} aria-hidden={copy ? true : undefined}>
                {SESSIONS.map(([a, b]) => <span key={a}><b>{a}</b> {b}</span>)}
              </div>
            ))}
          </div>
        </div>

        {/* Who it's for */}
        <section id="runners" className="lp-section scroll-mt-20">
          <div className="lp-wrap">
            <div className="mb-12 max-w-3xl">
              <span className="lp-kicker">Who it&apos;s for</span>
              <h2 className="lp-h2 mt-5">Your first 5K or your <em>fastest one.</em></h2>
              <p className="lp-lede mt-5">
                The same principles scale from 14 miles a week to 80: build slowly, keep easy days easy, make the hard days count.
                Pick a runner and see the week.
              </p>
            </div>
            <RunnerProfiles />
          </div>
        </section>

        {/* Pace lab */}
        <section id="paces" className="lp-section scroll-mt-20 pt-0">
          <div className="lp-wrap">
            <div className="mb-12 max-w-3xl">
              <span className="lp-kicker">Specific, not complicated</span>
              <h2 className="lp-h2 mt-5">Drag your goal. <em>Every pace follows.</em></h2>
              <p className="lp-lede mt-5">
                No &ldquo;3 rounds of 5×40 seconds at 4:12–4:44.&rdquo; One clear target per session, derived from the race you&apos;re
                training for.
              </p>
            </div>
            <PaceLab />
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="lp-section scroll-mt-20 pt-0">
          <div className="lp-wrap">
            <div className="mb-12 grid gap-6 lg:grid-cols-2 lg:items-end">
              <div>
                <span className="lp-kicker">How it works</span>
                <h2 className="lp-h2 mt-5">Two weeks at a time. <em>Never a rigid block.</em></h2>
              </div>
              <p className="lp-lede">
                Sixteen-week plans assume nothing goes wrong. Stride plans two weeks, watches how you respond, then writes the next two.
                You approve every block before it starts.
              </p>
            </div>
            <div className="lp-loop">
              {STEPS.map((s) => (
                <div key={s.n} className="lp-step">
                  <div className="lp-step-n">{s.n}</div>
                  <div className="mt-8 text-lg font-semibold tracking-[-0.02em]">{s.t}</div>
                  <p className="mt-2 text-[14.5px] leading-relaxed text-[var(--lp-muted)]">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Fail safe */}
        <section className="lp-section pt-0">
          <div className="lp-wrap grid gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
            <div>
              <span className="lp-kicker">Fail safe</span>
              <blockquote className="mt-6 text-[clamp(2rem,4.6vw,3.3rem)] leading-[1.06] tracking-[-0.02em]">
                <span className="lp-serif italic text-[var(--lp-cream)]">&ldquo;An undertrained runner races.</span>
                <span className="block font-semibold tracking-[-0.035em]">An injured one doesn&apos;t.&rdquo;</span>
              </blockquote>
              <p className="lp-lede mt-6">When the data is unclear, Stride prescribes less. These rules aren&apos;t suggestions to the AI; they&apos;re code it can&apos;t override.</p>
              <div className="mt-9 grid gap-3 sm:grid-cols-2">
                {GUARDS.map((g) => (
                  <div key={g.t} className="lp-guard">
                    <div className="lp-mono text-2xl font-medium text-[var(--lp-apricot)]">{g.k}</div>
                    <div className="mt-3 font-semibold">{g.t}</div>
                    <p className="mt-1 text-sm leading-relaxed text-[var(--lp-muted)]">{g.d}</p>
                  </div>
                ))}
              </div>
            </div>
            <Reveal className="lp-glass p-6 sm:p-8">
              <div className="text-xs uppercase tracking-[0.14em] text-[var(--lp-faint)]">Acute : chronic workload</div>
              <svg viewBox="0 0 200 120" className="mt-4 w-full" role="img" aria-label="Workload ratio gauge reading 1.08, inside the 0.8 to 1.3 safe range">
                <defs>
                  <linearGradient id="lp-arc" x1="0" x2="1">
                    <stop offset="0" stopColor="#4a5a7e" />
                    <stop offset=".45" stopColor="#ffb38a" />
                    <stop offset=".75" stopColor="#ff8c5a" />
                    <stop offset="1" stopColor="#e5484d" />
                  </linearGradient>
                </defs>
                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="14" strokeLinecap="round" />
                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="url(#lp-arc)" strokeWidth="14" strokeLinecap="round" opacity=".9" />
                {/* Safe band 0.8 to 1.3 on a 0 to 2 scale */}
                <path d="M71 10.6 A94 94 0 0 1 142.7 16.2" fill="none" stroke="#fff" strokeOpacity=".6" strokeWidth="2" strokeDasharray="2 3" />
                <g className="lp-needle" style={{ ["--angle" as string]: `${(1.08 / 2) * 180 - 90}deg` }}>
                  <line x1="100" y1="100" x2="100" y2="34" stroke="#fbe6da" strokeWidth="2.5" strokeLinecap="round" />
                </g>
                <circle cx="100" cy="100" r="6" fill="#fbe6da" />
              </svg>
              <div className="mt-2 flex items-end justify-between">
                <div>
                  <div className="lp-mono text-5xl font-medium">1.08</div>
                  <div className="mt-1 text-sm text-[#9be7bd]">In the safe range</div>
                </div>
                <p className="max-w-[22ch] text-right text-sm text-[var(--lp-faint)]">Above 1.3 and Stride trims the next week before you feel it.</p>
              </div>
            </Reveal>
          </div>
        </section>

        {/* Founder */}
        <section id="founder" className="lp-section scroll-mt-20 pt-0">
          <div className="lp-wrap grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-center lg:gap-16">
            <Reveal className="lp-reveal">
              {/* Drop a photo at public/founder.jpg and swap this monogram for <img src="/founder.jpg" alt="Jake Bowen" /> */}
              <div className="lp-portrait grid place-items-center">
                <span className="lp-serif text-[7rem] italic leading-none text-[rgba(251,230,218,0.9)]">JB</span>
                <div className="absolute inset-x-0 bottom-0 p-5">
                  <div className="lp-glass rounded-2xl p-4">
                    <div className="font-semibold">Jake Bowen</div>
                    <div className="text-sm text-[var(--lp-muted)]">Founder · CS student at Cal State Fullerton</div>
                  </div>
                </div>
              </div>
            </Reveal>
            <div>
              <span className="lp-kicker">The founder</span>
              <h2 className="lp-h2 mt-5">Built by a runner. <em>Tested on real miles first.</em></h2>
              <div className="mt-6 space-y-4 text-[1.0625rem] leading-relaxed text-[var(--lp-muted)]">
                <p>
                  I&apos;m Jake. I&apos;ve run a 2:58 marathon, I&apos;m chasing a sub-17 5K, and someday I want to finish a 100-miler.
                  Somewhere in 500 logged runs I got tired of plans that either felt generic or handed me paces I couldn&apos;t hit.
                </p>
                <p>
                  So I started writing the plan I actually wanted: simple sessions that look like what competitive runners do, a reason for
                  every one, and a coach that slows you down before an injury does. Now I&apos;d like to see if it works for you.
                </p>
              </div>
              <div className="mt-8 grid grid-cols-3 gap-3">
                {[["2:58", "Marathon"], ["70", "Peak mpw"], ["100", "Miles, next"]].map(([v, l]) => (
                  <div key={l} className="lp-stat">
                    <div className="lp-mono text-2xl font-medium sm:text-3xl">{v}</div>
                    <div className="mt-1 text-xs text-[var(--lp-faint)] sm:text-sm">{l}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Call to action + contact */}
        <section id="contact" className="lp-section scroll-mt-20 pt-0">
          <div className="lp-wrap">
            <div className="lp-cta">
              <div className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
                <div>
                  <span className="lp-kicker">Join the beta</span>
                  <h2 className="lp-h2 mt-5">Your next two weeks <em>are ready to write.</em></h2>
                  <p className="lp-lede mt-5">
                    Stride is free during an invite-only beta for a small group of runners. Connect Garmin Connect, set a goal, and approve
                    your first block.
                  </p>
                  <div className="mt-8 flex flex-wrap gap-3">
                    <Link href="/auth/register" className="lp-btn lp-btn-primary">Create your account <ArrowRight size={16} /></Link>
                    <Link href="/login" className="lp-btn lp-btn-ghost">Sign in</Link>
                    <a href={`mailto:${CONTACT}?subject=${encodeURIComponent("Stride beta invite")}`} className="lp-btn lp-btn-ghost">Request an invite</a>
                  </div>
                </div>
                <div className="space-y-4 text-[15px]">
                  <div className="text-xs uppercase tracking-[0.14em] text-[var(--lp-faint)]">Contact</div>
                  <a href={`mailto:${CONTACT}`} className="flex items-center gap-3 break-all"><Mail size={17} className="shrink-0 text-[var(--lp-apricot)]" />{CONTACT}</a>
                  <div className="flex items-center gap-3 text-[var(--lp-muted)]"><MapPin size={17} className="shrink-0 text-[var(--lp-apricot)]" />{LEGAL.location}</div>
                  <p className="text-sm leading-relaxed text-[var(--lp-faint)]">Questions about your data, the beta or a partnership: email me directly. I read everything.</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-foot">
        <div className="lp-wrap flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="lp-wordmark text-[15px] text-[var(--lp-text)]"><span className="lp-wordmark-dot" aria-hidden />Stride</span>
            <span>© {new Date().getFullYear()} {LEGAL.operator}</span>
          </div>
          <nav className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Legal">
            <Link href="/about">About</Link>
            <Link href="/privacy">Privacy</Link>
            <Link href="/terms">Terms</Link>
            <Link href="/login">Sign in</Link>
          </nav>
        </div>
        <p className="lp-wrap mt-5 text-xs">Garmin and Garmin Connect are trademarks of Garmin Ltd. or its subsidiaries. Stride is not affiliated with or endorsed by Garmin.</p>
      </footer>
    </div>
  );
}
