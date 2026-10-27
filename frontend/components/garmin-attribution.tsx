/**
 * Garmin brand guidelines: "Garmin [device model]" near any view of Garmin device data, and a
 * line on insights derived from it (docs/multi-user-design.md §3.2 #3). Plain text, no logo.
 */
export function GarminAttribution({ source, device, className }: { source?: string | null; device?: string | null; className?: string }) {
  if (source !== "garmin") return null;
  return <p className={className ?? "text-xs text-muted-foreground"}>Garmin{device ? ` ${device.replace(/^Garmin\s+/i, "")}` : ""}</p>;
}

export const DERIVED_FROM_GARMIN = "Insights derived in part from Garmin device-sourced data.";
