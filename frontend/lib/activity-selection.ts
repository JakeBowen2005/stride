/** Keep the coach tied to the same activity that supplies the displayed run's stats. */
export function primaryRunId(activities: { id: number; date: string; type: string; distance_miles: number; session?: unknown }[], today: string, matchedId?: number | null): number | undefined {
  if (matchedId != null) return matchedId;
  const runs = activities.filter(a => a.date.startsWith(today) && a.type !== "walk");
  const quality = runs.filter(a => a.session);
  return (quality.length ? quality : runs).reduce<typeof runs[number] | undefined>((best, a) => !best || a.distance_miles > best.distance_miles ? a : best, undefined)?.id;
}
