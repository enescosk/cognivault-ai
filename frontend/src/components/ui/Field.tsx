import type { InputHTMLAttributes, ReactNode } from "react";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  hint?: ReactNode;
}

export function Field({ label, hint, className = "", id, ...rest }: FieldProps) {
  return (
    <label className="ui-field" htmlFor={id}>
      {label && <span className="ui-field-label">{label}</span>}
      <input id={id} className={["ui-input", className].filter(Boolean).join(" ")} {...rest} />
      {hint && <span className="ui-field-hint">{hint}</span>}
    </label>
  );
}
