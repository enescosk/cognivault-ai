import type { ReactNode } from "react";

type Tone = "green" | "amber" | "red" | "accent" | "neutral";

interface StatusDotProps {
  tone?: Tone;
  pulse?: boolean;
  children?: ReactNode;
}

export function StatusDot({ tone = "neutral", pulse, children }: StatusDotProps) {
  const dotTone = tone === "neutral" ? "" : `ui-dot--${tone}`;
  const dot = <span className={["ui-dot", dotTone, pulse ? "ui-dot--pulse" : ""].filter(Boolean).join(" ")} />;
  if (!children) return dot;
  return (
    <span className="ui-status">
      {dot}
      {children}
    </span>
  );
}
