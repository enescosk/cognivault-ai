import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { Card } from "../Card";

describe("Card", () => {
  it("temel ui-card sınıfıyla, md padding'de ekstra sınıf olmadan render eder", () => {
    render(<Card>içerik</Card>);
    const card = screen.getByText("içerik");
    expect(card).toHaveClass("ui-card");
    expect(card.className).not.toMatch(/ui-card--pad-(sm|lg)/);
    expect(card.className).not.toMatch(/ui-card--(accent|hover)/);
  });

  it("accent ve hover modifier'larını uygular", () => {
    render(
      <Card accent hover>
        x
      </Card>,
    );
    expect(screen.getByText("x")).toHaveClass("ui-card--accent", "ui-card--hover");
  });

  it.each([
    ["sm", "ui-card--pad-sm"],
    ["lg", "ui-card--pad-lg"],
  ] as const)("pad=%s için %s sınıfını uygular", (pad, cls) => {
    render(<Card pad={pad}>x</Card>);
    expect(screen.getByText("x")).toHaveClass(cls);
  });

  it("HTML div attribute'larını geçirir (onClick, data-*)", () => {
    const onClick = vi.fn();
    render(
      <Card onClick={onClick} data-testid="kart">
        x
      </Card>,
    );
    const card = screen.getByTestId("kart");
    fireEvent.click(card);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
