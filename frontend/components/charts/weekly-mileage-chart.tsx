"use client";

import { useUnits } from "@/components/unit-preferences";
import { distanceValueInUnits, unitLabel } from "@/lib/units";

import { calendarMileage } from "@/lib/mileage-calendar";
import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { WeeklyMileage } from "@/lib/types";
import { cn } from "@/lib/utils";

export function WeeklyMileageChart({ data }: { data: WeeklyMileage[] }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const [window, setWindow] = useState(12);
  const [showData, setShowData] = useState(false);
  const formatted = calendarMileage(data,window).map((d) => ({
    ...d, actual: distanceValueInUnits(d.actual, units), label: new Date(d.week_start+"T12:00:00").toLocaleDateString("en-US", {month:"short",day:"numeric"}),
  }));
  const total = formatted.reduce((sum,d) => sum+d.actual,0);
  return <div className="space-y-3 px-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-xs text-muted-foreground"><span className="font-mono text-base font-semibold text-foreground">{total.toFixed(1)}</span> {unit} across {formatted.length} calendar weeks · current week in progress</p>
      <div className="flex gap-1 rounded-lg bg-muted p-1" aria-label="Mileage history range">{[4,8,12].map((n) => <button key={n} type="button" aria-pressed={window===n} onClick={() => setWindow(n)} className={cn("min-h-9 rounded-md px-3 text-xs font-medium transition-colors",window===n?"bg-card text-primary":"text-muted-foreground hover:text-foreground")}>{n}w</button>)}</div>
    </div>
    {data.length ? <ResponsiveContainer width="100%" height={200}>
      <BarChart data={formatted} barGap={2} accessibilityLayer>
        <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="label" tick={{fontSize:11}} axisLine={false} tickLine={false} />
        <YAxis tick={{fontSize:11}} axisLine={false} tickLine={false} width={32}/>
        <Tooltip cursor={{fill:"var(--muted)"}} contentStyle={{backgroundColor:"var(--card)",border:"1px solid var(--border)",borderRadius:8,fontSize:12}} formatter={(value) => [`${value} ${unit}`,"Completed"]}/>
        <Bar dataKey="actual" fill="var(--viz-series-1)" radius={[4,4,0,0]} name="Completed" maxBarSize={38}/>
      </BarChart>
    </ResponsiveContainer>:<p className="py-8 text-center text-sm text-muted-foreground">Your mileage history will appear after runs are logged.</p>}
    <button type="button" aria-expanded={showData} onClick={() => setShowData(!showData)} className="min-h-10 text-xs font-medium text-primary">{showData?"Hide weekly totals":"See weekly totals"}</button>
    {showData && <dl className="grid grid-cols-2 gap-2 rounded-lg bg-muted/50 p-3 sm:grid-cols-4">{formatted.map((d) => <div key={d.week_start}><dt className="text-xs text-muted-foreground">Week of {d.label}</dt><dd className="font-mono text-sm">{d.actual.toFixed(1)} {unit}</dd></div>)}</dl>}
  </div>;
}
