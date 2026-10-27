import type { Metadata } from "next";
import Link from "next/link";
import { CONTACT, LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Privacy Policy · Stride",
  description: "What Stride collects, why, who processes it, how long it is kept, and your choices.",
};

// Public: reviewers (and anyone deciding whether to connect Garmin) read this signed out.
// Update it before the app changes what it collects or who processes it.
export default function PrivacyPage() {
  return (
    <article className="glass mx-auto w-full max-w-3xl space-y-6 p-5 text-sm leading-relaxed sm:p-8 [&_h2]:pt-2 [&_h2]:text-base [&_h2]:font-bold [&_li]:ml-5 [&_li]:list-disc [&_ul]:space-y-1.5">
      <header className="space-y-2">
        <h1 className="display">Privacy Policy</h1>
        <p className="text-muted-foreground">Effective {LEGAL.effectiveDate}</p>
      </header>

      <p>
        Stride (&ldquo;Stride&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;) is a running coach app operated by {LEGAL.operator}, {LEGAL.location}.
        This policy explains what we collect, why we collect it, who processes it, how long we keep it, and the choices you have.
        Stride is currently an invite-only beta.
      </p>
      <p className="glass-tile rounded-xl p-3.5">
        <strong>The short version:</strong> we use your running and recovery data only to coach you. We don&apos;t sell it, we don&apos;t
        use it for advertising, and we don&apos;t run analytics or tracking tools. You can download or delete your data from Settings at any time.
      </p>

      <section className="space-y-3">
        <h2>1. Information we collect</h2>
        <p><strong>Account information.</strong> Your name, email address and password. Passwords are stored only as an Argon2 hash, never in readable form.</p>
        <p>
          <strong>What you tell us.</strong> Your age, how long you&apos;ve been running, your weekly mileage, personal records, goals and race dates,
          the days and time you have to run, units and workout-format preferences, and your time zone. Also the comments you write about your
          runs and anything you send to the coach.
        </p>
        <p><strong>Garmin Connect data</strong>, if you connect your Garmin account:</p>
        <ul>
          <li><em>Activities:</em> your runs, including date, distance, duration, pace, heart rate, elevation, cadence, running form metrics, training effect and load, laps from the activity file, and the post-run feel and effort rating from your watch.</li>
          <li><em>Health:</em> daily summaries, including resting heart rate, sleep (duration, stages, score), heart-rate variability, stress, Body Battery, steps, respiration and Garmin&apos;s training readiness and load figures.</li>
        </ul>
        <p>We read only running activities for training; Stride doesn&apos;t use other sports. We receive data only for the periods Garmin makes available, and only while you stay connected.</p>
        <p><strong>Files you upload.</strong> Activity (.FIT) files you import yourself.</p>
        <p>
          <strong>Technical information.</strong> A session cookie that keeps you signed in (section 6). To limit repeated sign-in attempts, we keep
          short-lived, hashed counters based on your email and network address. We don&apos;t keep general access logs about you for any other purpose.
        </p>
      </section>

      <section className="space-y-3">
        <h2>2. How we use it</h2>
        <ul>
          <li>To build and adjust your training plan, check how each run matched what was prescribed, and flag fatigue or injury risk.</li>
          <li>To show your history, charts and weekly summaries.</li>
          <li>To run optional AI coaching reviews if you turn them on (section 3).</li>
          <li>To keep the service secure and working, and to restore it from backups after a failure.</li>
        </ul>
        <p>We don&apos;t sell your data, share it with data brokers or advertisers, use it for advertising, or use it to train AI models.</p>
      </section>

      <section className="space-y-3">
        <h2>3. AI coaching reviews (optional, off by default)</h2>
        <p>
          Stride&apos;s training decisions come from fixed training rules, not from AI. If you opt in, Stride sends a summary of your recent training
          to <strong>OpenAI</strong> so a model can explain those decisions in plain language. The summary includes your recent runs and laps, watch
          feel and effort, recovery metrics, your plan and goal, and your run comments.
        </p>
        <p>
          Requests are sent with OpenAI&apos;s response storage disabled. Under OpenAI&apos;s API data policy, API data isn&apos;t used to train their
          models. The AI can&apos;t change your training on its own, and Stride works fully without it. You can turn AI reviews off in Settings at any time.
        </p>
      </section>

      <section className="space-y-3">
        <h2>4. Service providers that process your data</h2>
        <p>We share data only with providers that help us run Stride. They process it on our behalf:</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[30rem] text-left [&_td]:border-t [&_td]:border-[var(--glass-border)] [&_td]:py-2 [&_td]:pr-3 [&_td]:align-top [&_th]:pb-2 [&_th]:pr-3">
            <thead><tr><th>Provider</th><th>What it does</th><th>Data involved</th></tr></thead>
            <tbody>
              <tr><td><strong>Garmin</strong></td><td>Source of your activity and health data, at your request</td><td>Your Garmin data, and the request for it</td></tr>
              <tr><td><strong>Render</strong> (United States)</td><td>Hosts the app and its database</td><td>Everything stored in Stride</td></tr>
              <tr><td><strong>OpenAI</strong> (only if you opt in)</td><td>Writes coaching explanations</td><td>The training summary described in section 3</td></tr>
              <tr><td><strong>Amazon Web Services S3</strong> (United States)</td><td>Encrypted backups and stored activity files</td><td>Database backups; .FIT files</td></tr>
            </tbody>
          </table>
        </div>
        <p>
          We may also disclose information if the law requires it, or to protect the safety of a person. If Stride is ever sold or merged, this
          policy would continue to apply to your existing data, and we would tell you before anything changed.
        </p>
      </section>

      <section className="space-y-3">
        <h2>5. How long we keep it</h2>
        <ul>
          <li><strong>While your account is open,</strong> we keep your training history, because long-term trends are part of the coaching.</li>
          <li><strong>Temporary analysis caches</strong> are removed after 45 days.</li>
          <li><strong>Server backups</strong> are taken every 6 hours, and only the most recent 7 are kept on the server. Off-site backups are deleted after {LEGAL.offsiteBackupDays} days.</li>
          <li><strong>When you delete your account,</strong> your training data and Garmin connection are removed from the live system immediately. Copies in backups disappear as those backups expire, within the windows above.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2>6. Cookies and local storage</h2>
        <p>
          Stride uses one essential cookie, a sign-in session that lasts up to 7 days. It is HTTP-only and secure. The app also remembers a few
          display choices (such as which chart range you picked) in your browser&apos;s local storage. We use no advertising, analytics or
          third-party tracking cookies.
        </p>
      </section>

      <section className="space-y-3">
        <h2>7. Your choices and rights</h2>
        <ul>
          <li><strong>Download your data:</strong> Settings → <em>Download my training data</em>.</li>
          <li><strong>Delete your account:</strong> Settings → <em>Delete my account</em>.</li>
          <li><strong>Disconnect Garmin:</strong> in Settings in Stride, or in Garmin Connect&apos;s connected-apps settings. Disconnecting stops new data from arriving.</li>
          <li><strong>Turn AI reviews off:</strong> in Settings.</li>
          <li><strong>Correct your information:</strong> edit your profile and goals in Settings, or contact us.</li>
        </ul>
        <p>
          Depending on where you live (for example, California or the EU/UK), you may have rights to access, correct, delete or move your data,
          and to object to or restrict how we use it. You can use any of these rights by contacting us. We won&apos;t treat you differently for
          using them. We don&apos;t sell or &ldquo;share&rdquo; personal information as California law defines those terms.
        </p>
      </section>

      <section className="space-y-3">
        <h2>8. Security</h2>
        <p>
          Data is sent over HTTPS. Garmin connection credentials are encrypted at rest. Passwords are hashed with Argon2, and sign-in attempts
          are rate-limited. Access to production systems is limited to the operator. No system is perfectly secure. If a breach affects your
          data, we will notify you as the law requires.
        </p>
      </section>

      <section className="space-y-3">
        <h2>9. Children</h2>
        <p>Stride is not intended for children under 16, and we don&apos;t knowingly collect their data. If you believe a child has given us information, contact us and we will delete it.</p>
      </section>

      <section className="space-y-3">
        <h2>10. International users</h2>
        <p>Stride is operated from, and stores data in, the United States. If you use it from elsewhere, your data is transferred to and processed in the United States.</p>
      </section>

      <section className="space-y-3">
        <h2>11. Changes to this policy</h2>
        <p>We will post any update here with a new effective date. For a material change, we will notify you in the app or by email before it takes effect.</p>
      </section>

      <section className="space-y-3">
        <h2>12. Contact</h2>
        <p>{LEGAL.operator} · {LEGAL.contactEmail ? <a className="underline underline-offset-2" href={`mailto:${LEGAL.contactEmail}`}>{CONTACT}</a> : CONTACT} · {LEGAL.location}</p>
      </section>

      <footer className="space-y-2 border-t border-[var(--glass-border)] pt-4 text-xs text-muted-foreground">
        <p>Garmin, Garmin Connect and Body Battery are trademarks of Garmin Ltd. or its subsidiaries. Stride is not affiliated with or endorsed by Garmin.</p>
        <p><Link className="underline underline-offset-2" href="/about">About Stride</Link></p>
      </footer>
    </article>
  );
}
