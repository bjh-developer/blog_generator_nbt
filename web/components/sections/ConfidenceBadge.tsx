import { Badge } from "@/components/ui/badge";
import { palette } from "@/lib/theme";
import { Check, AlertTriangle } from "lucide-react";

export function ConfidenceBadge({ confidence }: { confidence: number }) {
  const verified = confidence >= 0.6;
  const pct = Math.round(confidence * 100);
  return (
    <Badge
      title={verified ? "Grounded in sources" : "Low confidence"}
      className="text-white"
      style={{ background: verified ? palette.blue : palette.orange }}
    >
      {verified ? <Check size={12} /> : <AlertTriangle size={12} />} {pct}%
    </Badge>
  );
}
