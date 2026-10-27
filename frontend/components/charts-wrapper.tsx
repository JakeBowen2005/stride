"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WeeklyMileageChart } from "@/components/charts/weekly-mileage-chart";
import { MileageOverTimeChart } from "@/components/charts/mileage-over-time-chart";
import { AerobicEfficiencyChart } from "@/components/charts/aerobic-efficiency-chart";
import type { WeeklyMileage } from "@/lib/types";

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

export function MileageOverTimeChartWrapper({ revision }: { revision: number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Mileage Over Time</CardTitle>
      </CardHeader>
      <CardContent className="pl-0 pr-2">
        <MileageOverTimeChart revision={revision} />
      </CardContent>
    </Card>
  );
}

export function AerobicEfficiencyChartWrapper({ revision }: { revision: number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Aerobic Efficiency</CardTitle>
      </CardHeader>
      <CardContent className="pl-0 pr-2">
        <AerobicEfficiencyChart revision={revision} />
      </CardContent>
    </Card>
  );
}
