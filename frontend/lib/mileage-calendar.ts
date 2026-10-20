import { localDateStr } from "@/lib/format";
import type { WeeklyMileage } from "@/lib/types";

/** Calendar weeks, including no-run weeks and the current partial week. */
export function calendarMileage(data: WeeklyMileage[], count: number, today = new Date()): WeeklyMileage[] {
  const monday = new Date(today.getFullYear(),today.getMonth(),today.getDate(),12);
  monday.setDate(monday.getDate() - (monday.getDay()+6)%7);
  const byWeek = new Map(data.map((d) => [d.week_start.slice(0,10),d]));
  return Array.from({length:count},(_,index) => {
    const week = new Date(monday);
    week.setDate(week.getDate() - (count-1-index)*7);
    const key=localDateStr(week);
    return byWeek.get(key) ?? {week_start:key,actual:0,planned:0};
  });
}
