/** Who operates Stride, as shown on the public privacy and about pages.
 * `contactEmail` must be set before the privacy URL is given to Garmin or anyone else. */
export const LEGAL = {
  operator: "Jake Bowen (Stride)",
  location: "California, United States",
  contactEmail: "jakeeb05@gmail.com",
  effectiveDate: "October 27, 2026",
  /** The privacy policy changes independently of the terms (Oct 29: unofficial Garmin metrics removed). */
  privacyEffectiveDate: "October 29, 2026",
  /** Recorded on each account at registration; keep equal to TERMS_VERSION in backend/app/api/auth.py. */
  termsVersion: "2026-10-27",
  /** Keep in sync with the S3 bucket's lifecycle rule for off-site backups. */
  offsiteBackupDays: 30,
};

export const CONTACT = LEGAL.contactEmail || "[contact email]";
