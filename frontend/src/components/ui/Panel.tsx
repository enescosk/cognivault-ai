import type { ReactNode } from "react";

interface PanelProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function Panel({ title, subtitle, actions, footer, children, className = "" }: PanelProps) {
  const showHead = title || subtitle || actions;
  return (
    <section className={["ui-panel", className].filter(Boolean).join(" ")}>
      {showHead && (
        <header className="ui-panel-head">
          <div>
            {title && <div className="ui-panel-title">{title}</div>}
            {subtitle && <div className="ui-panel-sub">{subtitle}</div>}
          </div>
          {actions && <div style={{ flexShrink: 0 }}>{actions}</div>}
        </header>
      )}
      {children && <div className="ui-panel-body">{children}</div>}
      {footer && <footer className="ui-panel-foot">{footer}</footer>}
    </section>
  );
}
