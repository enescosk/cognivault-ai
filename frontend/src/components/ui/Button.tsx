import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "subtle" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  block?: boolean;
}

const sizeClass: Record<Size, string> = { sm: "ui-btn--sm", md: "", lg: "ui-btn--lg" };

export function Button({ variant = "ghost", size = "md", block, className = "", ...rest }: ButtonProps) {
  const cls = ["ui-btn", `ui-btn--${variant}`, sizeClass[size], block ? "ui-btn--block" : "", className]
    .filter(Boolean)
    .join(" ");
  return <button className={cls} {...rest} />;
}
