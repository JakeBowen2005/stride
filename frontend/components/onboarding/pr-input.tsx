"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { RaceDistance } from "@/lib/types";

interface PREntry {
  distance: RaceDistance | "";
  hours: string;
  minutes: string;
  seconds: string;
}

interface PRInputProps {
  entries: PREntry[];
  onChange: (entries: PREntry[]) => void;
}

export type { PREntry };

export function PRInput({ entries, onChange }: PRInputProps) {
  function updateEntry(index: number, field: keyof PREntry, value: string) {
    const updated = [...entries];
    updated[index] = { ...updated[index], [field]: value };
    onChange(updated);
  }

  function addEntry() {
    onChange([...entries, { distance: "", hours: "", minutes: "", seconds: "" }]);
  }

  function removeEntry(index: number) {
    onChange(entries.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-3">
      {entries.map((entry, i) => (
        <div key={i} className="flex items-center gap-2">
          <Select
            value={entry.distance}
            onValueChange={(v) => updateEntry(i, "distance", v ?? "")}
          >
            <SelectTrigger className="w-36">
              <SelectValue placeholder="Distance" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="5k">5K</SelectItem>
              <SelectItem value="10k">10K</SelectItem>
              <SelectItem value="half">Half Marathon</SelectItem>
              <SelectItem value="marathon">Marathon</SelectItem>
            </SelectContent>
          </Select>
          <Input
            type="number"
            placeholder="H"
            className="w-14 font-mono"
            value={entry.hours}
            onChange={(e) => updateEntry(i, "hours", e.target.value)}
            min={0}
            max={9}
          />
          <span className="text-muted-foreground">:</span>
          <Input
            type="number"
            placeholder="MM"
            className="w-16 font-mono"
            value={entry.minutes}
            onChange={(e) => updateEntry(i, "minutes", e.target.value)}
            min={0}
            max={59}
          />
          <span className="text-muted-foreground">:</span>
          <Input
            type="number"
            placeholder="SS"
            className="w-16 font-mono"
            value={entry.seconds}
            onChange={(e) => updateEntry(i, "seconds", e.target.value)}
            min={0}
            max={59}
          />
          {entries.length > 1 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => removeEntry(i)}
              className="text-muted-foreground"
            >
              Remove
            </Button>
          )}
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={addEntry}>
        Add PR
      </Button>
    </div>
  );
}
