import type { HTMLAttributes } from "react";

type Pad = "sm" | "md" | "lg";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  accent?: boolean;
  hover?: boolean;
  pad?: Pad;
}

const padClass: Record<Pad, string> = { sm: "ui-card--pad-sm", md: "", lg: "ui-card--pad-lg" };

export function Card({ accent, hover, pad = "md", className = "", ...rest }: CardProps) {
  const cls = ["ui-card", accent ? "ui-card--accent" : "", hover ? "ui-card--hover" : "", padClass[pad], className]
    .filter(Boolean)
    .join(" ");
  return <div className={cls} {...rest} />;
}
