import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "solid" | "outline" | "ghost";
}

export function Button({ className, variant = "solid", ...props }: ButtonProps) {
  const variants = {
    solid: "bg-ink text-white hover:bg-ink/90",
    outline: "border border-current bg-transparent hover:bg-current/10",
    ghost: "bg-transparent hover:bg-ink/5",
  };
  return (
    <button
      className={cn(
        "inline-flex items-center gap-2 rounded-pill px-4 py-2 text-sm font-semibold transition-colors duration-200 cursor-pointer",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
