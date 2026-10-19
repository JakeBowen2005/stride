import { Card, CardContent } from "@/components/ui/card";
import type { Wellness } from "@/components/home/types";

function fmt(sec?: number | null) {
  if (!sec) return "—";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

export function RacePredictions({
  wellness,
  prs,
  goal,
}: {
  wellness: Wellness | null;
  prs: Record<string, number>;
  goal: { distance: string | null; target_time: number | null } | null;
}) {
  if (!wellness?.predicted_5k) return null;
  const rows = [
    { key: "5k", label: "5K", pred: wellness.predicted_5k, pr: prs["5K"] },
    { key: "10k", label: "10K", pred: wellness.predicted_10k, pr: prs["10K"] },
    { key: "half", label: "Half", pred: wellness.predicted_half, pr: prs["Half Marathon"] },
    { key: "marathon", label: "Marathon", pred: wellness.predicted_marathon, pr: prs["Marathon"] },
  ];
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="mb-2 flex items-baseline justify-between">
          <h3 className="text-sm font-medium">Race Predictions</h3>
          <span className="text-xs text-muted-foreground">Garmin, based on current fitness</span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="pb-1 font-medium">Distance</th>
              <th className="pb-1 text-right font-medium">Predicted</th>
              <th className="pb-1 text-right font-medium">PR</th>
              <th className="pb-1 text-right font-medium">Goal</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t">
                <td className="py-1.5">{r.label}</td>
                <td className="py-1.5 text-right font-mono">{fmt(r.pred)}</td>
                <td className="py-1.5 text-right font-mono text-muted-foreground">{fmt(r.pr)}</td>
                <td className="py-1.5 text-right font-mono">{goal?.distance === r.key ? fmt(goal.target_time) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-muted-foreground">
          Predictions dip during a rebuild and climb as fitness returns. Use them to track the trend, not to set race pace.
        </p>
      </CardContent>
    </Card>
  );
}
