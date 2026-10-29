import type { Metadata } from "next";
import Link from "next/link";
import { CONTACT, LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Terms of Service · Stride",
  description: "The agreement between you and Stride: what the service is, what it isn't, and the limits of liability.",
};

// Public, like /privacy. Garmin's developer agreement §5.3 requires a written agreement with each end user
// that protects Garmin at least as much as Garmin's own terms. Bump LEGAL.termsVersion (and the backend
// TERMS_VERSION) whenever this changes, so registration records which version was accepted.
export default function TermsPage() {
  return (
    <article className="glass mx-auto w-full max-w-3xl space-y-6 p-5 text-sm leading-relaxed sm:p-8 [&_h2]:pt-2 [&_h2]:text-base [&_h2]:font-bold [&_li]:ml-5 [&_li]:list-disc [&_ul]:space-y-1.5">
      <header className="space-y-2">
        <h1 className="display">Terms of Service</h1>
        <p className="text-muted-foreground">Effective {LEGAL.effectiveDate} · version {LEGAL.termsVersion}</p>
      </header>

      <p>
        These terms are an agreement between you and {LEGAL.operator} (&ldquo;Stride&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;), {LEGAL.location}.
        By creating an account or using Stride, you agree to them. If you don&apos;t agree, don&apos;t use Stride. Stride is an invite-only beta.
      </p>

      <section className="space-y-3">
        <h2>1. What Stride is</h2>
        <p>
          Stride is a running training app. It builds training plans from rules and the information you give it or connect to it (for example,
          from Garmin Connect), and it can optionally explain its decisions with an AI model. Features may change, and Stride may be unavailable at times.
        </p>
      </section>

      <section className="space-y-3">
        <h2>2. Not medical advice</h2>
        <p>
          Stride gives general training information, not medical advice, diagnosis or treatment. Running carries a risk of injury. Check with a
          medical professional before starting or changing a training program, especially if you have a health condition, are returning from
          injury, or are pregnant. Stop running and get medical help if you have chest pain, dizziness, fainting, unusual shortness of breath, or
          pain that changes how you run. You decide what you actually run; follow any plan at your own risk and adjust it to how you feel.
        </p>
      </section>

      <section className="space-y-3">
        <h2>3. Your account</h2>
        <ul>
          <li>You must be at least 16. Keep your password private; you are responsible for activity on your account.</li>
          <li>Give accurate information, especially about your health, fitness and training history. The plan is only as good as what it is told.</li>
          <li>You can delete your account at any time from Settings. The <Link className="underline underline-offset-2" href="/privacy">privacy policy</Link> explains what happens to your data.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2>4. Acceptable use</h2>
        <p>Don&apos;t misuse Stride. In particular, don&apos;t:</p>
        <ul>
          <li>access another person&apos;s account or data, or try to;</li>
          <li>probe, overload or attack the service, or get around its limits or security;</li>
          <li>copy, resell or scrape the service or data from it, or use it to build a competing product;</li>
          <li>upload anything unlawful or that you don&apos;t have the right to upload.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2>5. Third-party services, including Garmin</h2>
        <p>
          If you connect Garmin Connect, your use of Garmin&apos;s products is also governed by Garmin&apos;s own terms and privacy notice.
          Garmin Ltd. and its subsidiaries (&ldquo;Garmin&rdquo;) are not a party to these terms and are not responsible for Stride. Data from
          Garmin is provided &ldquo;as is&rdquo;: <strong>Garmin makes no warranties</strong> about it or about Stride, and, to the fullest extent the law
          allows, <strong>Garmin has no liability to you</strong> arising from Stride or from your use of Garmin data in Stride. Garmin is an intended
          third-party beneficiary of this section and may enforce it. OpenAI processes data only if you turn on AI coaching.
        </p>
      </section>

      <section className="space-y-3">
        <h2>6. Disclaimers</h2>
        <p>
          Stride is provided <strong>&ldquo;as is&rdquo; and &ldquo;as available&rdquo;</strong>, without warranties of any kind, express or implied,
          including fitness for a particular purpose, accuracy and non-infringement. We don&apos;t promise that a plan will reach a goal, prevent
          injury, or that data from devices and providers is accurate or complete.
        </p>
      </section>

      <section className="space-y-3">
        <h2>7. Limitation of liability</h2>
        <p>
          To the fullest extent the law allows, Stride and its operator will not be liable for any indirect, incidental, special, consequential or
          punitive damages, or for any injury, loss of data, or loss of profits, arising from your use of Stride or any training it suggests.
          Our total liability for any claim is limited to the greater of the amount you paid us in the 12 months before the claim or US $50.
          Some places don&apos;t allow these limits, so they may not fully apply to you.
        </p>
      </section>

      <section className="space-y-3">
        <h2>8. Ending the agreement</h2>
        <p>
          You can stop using Stride and delete your account at any time. We may suspend or end your access if you break these terms, if the beta
          ends, or if we must to comply with the law or with a provider&apos;s requirements. Sections 2, 5, 6, 7 and 9 survive.
        </p>
      </section>

      <section className="space-y-3">
        <h2>9. General</h2>
        <p>
          These terms are governed by the laws of California, United States, without regard to conflict-of-law rules. We may update them; we
          will post the new version here and, for a material change, tell you in the app before it takes effect. Continuing to use Stride after
          that means you accept the update.
        </p>
      </section>

      <section className="space-y-3">
        <h2>10. Contact</h2>
        <p>{LEGAL.operator} · {LEGAL.contactEmail ? <a className="underline underline-offset-2" href={`mailto:${LEGAL.contactEmail}`}>{CONTACT}</a> : CONTACT} · {LEGAL.location}</p>
      </section>

      <footer className="space-y-2 border-t border-[var(--glass-border)] pt-4 text-xs text-muted-foreground">
        <p>Garmin and Garmin Connect are trademarks of Garmin Ltd. or its subsidiaries. Stride is not affiliated with or endorsed by Garmin.</p>
        <p><Link className="underline underline-offset-2" href="/privacy">Privacy policy</Link> · <Link className="underline underline-offset-2" href="/about">About Stride</Link></p>
      </footer>
    </article>
  );
}
