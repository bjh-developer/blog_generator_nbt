import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill px-3 py-1 text-xs font-bold uppercase tracking-wide",
        className,
      )}
      style={style}
      {...props}
    />
  );
}
