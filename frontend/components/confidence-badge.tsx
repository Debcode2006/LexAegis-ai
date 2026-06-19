import { cn } from "@/lib/utils";

export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone =
    value >= 0.7 ? "bg-green-100 text-green-800" : value >= 0.4 ? "bg-amber-100 text-amber-800" : "bg-red-100 text-red-800";
  return (
    <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", tone)}>
      Confidence {pct}%
    </span>
  );
}
