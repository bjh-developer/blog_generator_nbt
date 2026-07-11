import { Sparkles, type LucideIcon } from "lucide-react";

// Shared section kicker. Replaces the ad-hoc "✦" glyph so every section
// uses a consistent vector icon + label (no emoji/unicode-glyph icons).
export function Eyebrow({
  children,
  icon: Icon = Sparkles,
  color = "#ff914d",
}: {
  children: React.ReactNode;
  icon?: LucideIcon;
  color?: string;
}) {
  return (
    <p
      className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-widest"
      style={{ color }}
    >
      <Icon size={15} aria-hidden className="shrink-0" />
      {children}
    </p>
  );
}
