import type { Metadata } from "next";
import Link from "next/link";
import { CONTACT, LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "About Stride · Running coach",
  description: "Stride builds two-week rolling training plans for runners and adapts them to what you actually ran.",
};

const POINTS = [
  { title: "Running only", text: "Every plan, workout and chart is about running. No cycling, swimming or gym sessions." },
  { title: "Rolling two-week plans", text: "Stride plans two weeks at a time and adjusts the next block to how you responded. You approve every block before it starts." },
  { title: "Real workouts", text: "Sessions look like what competitive runners do: \"6x800m at 5K pace with 90s jog\", with a warmup, a cooldown and the reason it's on the plan." },
  { title: "Your watch is the truth", text: "Runs sync from Garmin Connect. Stride reads the measured laps and your watch's post-run feel and effort to decide whether the next hard day holds, progresses or eases off." },
  { title: "Fail safe", text: "Conservative mileage ramps, deload weeks, no back-to-back hard days, and recovery flags from sleep and HRV. When in doubt, Stride prescribes less." },
  { title: "AI explains, rules decide", text: "Training decisions come from fixed training rules. An optional AI review explains them in plain language; it can't change your plan on its own." },
];

// Public landing page (the company website for partner applications). Signed-out visitors land here.
export default function AboutPage() {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <section className="glass space-y-4 p-5 sm:p-8">
        <h1 className="display">Stride</h1>
        <p className="text-lg leading-snug">A running coach that plans two weeks at a time and adapts to what you actually ran.</p>
        <p className="text-sm text-muted-foreground">
          Stride is in a free, invite-only beta for a small group of runners. It connects to Garmin Connect, checks each run against the planned
          session, and adjusts the plan with conservative, science-based training rules.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <Link href="/login" className="inline-flex min-h-11 items-center rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground">Sign in</Link>
          <Link href="/privacy" className="inline-flex min-h-11 items-center rounded-full border border-[var(--glass-border)] bg-[var(--glass-inner)] px-5 text-sm font-semibold">Privacy policy</Link>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        {POINTS.map((p) => (
          <div key={p.title} className="glass-tile space-y-1.5 rounded-2xl p-4">
            <h2 className="text-sm font-bold">{p.title}</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">{p.text}</p>
          </div>
        ))}
      </section>

      <section className="glass space-y-2 p-5 text-sm sm:p-6">
        <h2 className="text-base font-bold">Your data</h2>
        <p className="text-muted-foreground">
          Stride uses your running and recovery data only to coach you. It is never sold or used for advertising, and you can download or
          delete it from Settings at any time. See the <Link className="underline underline-offset-2" href="/privacy">privacy policy</Link> and <Link className="underline underline-offset-2" href="/terms">terms of service</Link>.
        </p>
      </section>

      <footer className="space-y-1 px-1 pb-4 text-xs text-muted-foreground">
        <p>Operated by {LEGAL.operator}, {LEGAL.location} · {LEGAL.contactEmail ? <a className="underline underline-offset-2" href={`mailto:${LEGAL.contactEmail}`}>{CONTACT}</a> : CONTACT}</p>
        <p>Garmin and Garmin Connect are trademarks of Garmin Ltd. or its subsidiaries. Stride is not affiliated with or endorsed by Garmin.</p>
      </footer>
    </div>
  );
}
