import { formatDistance } from "@/lib/format";

export type Units = "miles" | "km";
export const unitLabel = (units: Units) => units === "km" ? "km" : "mi";
export const distanceInUnits = (miles: number, units: Units) => formatDistance(miles * (units === "km" ? 1.60934 : 1));
export function paceInUnits(pace: string, units: Units): string {
  if (units !== "km") return pace;
  return pace.replace(/(\d+):(\d{2})/g, (_, m, s) => {
    const total = Math.round((Number(m)*60+Number(s))/1.60934);
    return `${Math.floor(total/60)}:${String(total%60).padStart(2,"0")}`;
  });
}
