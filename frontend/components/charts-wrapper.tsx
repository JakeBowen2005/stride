"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WeeklyMileageChart } from "@/components/charts/weekly-mileage-chart";
import { PaceVsTargetChart } from "@/components/charts/pace-vs-target-chart";
import { MileageOverTimeChart } from "@/components/charts/mileage-over-time-chart";
import type { WeeklyMileage, PaceVsTarget } from "@/lib/types";

export function WeeklyMileageChartWrapper({ data, showTitle = true }: { data: WeeklyMileage[]; showTitle?: boolean }) {
  return (
    <Card>
      {showTitle && <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Weekly Mileage</CardTitle>
      </CardHeader>}
      <CardContent className={showTitle ? "pl-0 pr-2" : "pl-0 pr-2 pt-3"}>
        <WeeklyMileageChart data={data} />
      </CardContent>
    </Card>
  );
}

export function PaceVsTargetChartWrapper({ data }: { data: PaceVsTarget[] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Pace vs Target</CardTitle>
      </CardHeader>
      <CardContent className="pl-0 pr-2">
        <PaceVsTargetChart data={data} />
      </CardContent>
    </Card>
  );
}

export function MileageOverTimeChartWrapper({ data }: { data: WeeklyMileage[] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Mileage Over Time</CardTitle>
      </CardHeader>
      <CardContent className="pl-0 pr-2">
        <MileageOverTimeChart data={data} />
      </CardContent>
    </Card>
  );
}
