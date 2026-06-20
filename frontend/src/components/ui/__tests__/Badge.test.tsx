import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Badge } from "../Badge";

describe("Badge", () => {
  it("varsayılan olarak neutral tonla render eder", () => {
    render(<Badge>onaylı</Badge>);
    const badge = screen.getByText("onaylı");
    expect(badge.tagName).toBe("SPAN");
    expect(badge).toHaveClass("ui-badge", "ui-badge--neutral");
  });

  it.each([
    ["accent", "ui-badge--accent"],
    ["green", "ui-badge--green"],
    ["amber", "ui-badge--amber"],
    ["red", "ui-badge--red"],
    ["purple", "ui-badge--purple"],
  ] as const)("%s tonu için %s sınıfını uygular", (tone, cls) => {
    render(<Badge tone={tone}>x</Badge>);
    expect(screen.getByText("x")).toHaveClass(cls);
  });

  it("ekstra className'i birleştirir", () => {
    render(<Badge className="iz">x</Badge>);
    expect(screen.getByText("x")).toHaveClass("ui-badge", "iz");
  });

  it("ReactNode children'ı render eder", () => {
    render(
      <Badge>
        <strong>92%</strong>
      </Badge>,
    );
    expect(screen.getByText("92%").tagName).toBe("STRONG");
  });
});
