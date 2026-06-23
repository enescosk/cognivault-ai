import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { StatusDot } from "../StatusDot";

describe("StatusDot", () => {
  it("children yoksa yalnız çıplak noktayı render eder (sarmalayıcı yok)", () => {
    const { container } = render(<StatusDot tone="green" />);
    expect(container.querySelector(".ui-status")).toBeNull();
    const dot = container.querySelector(".ui-dot");
    expect(dot).not.toBeNull();
    expect(dot).toHaveClass("ui-dot--green");
  });

  it("children varsa nokta + etiketi ui-status içinde sarmalar", () => {
    const { container } = render(<StatusDot tone="amber">Bekliyor</StatusDot>);
    const wrap = container.querySelector(".ui-status");
    expect(wrap).not.toBeNull();
    expect(wrap?.querySelector(".ui-dot--amber")).not.toBeNull();
    expect(screen.getByText("Bekliyor")).toBeInTheDocument();
  });

  it("neutral ton için ekstra ton sınıfı eklemez", () => {
    const { container } = render(<StatusDot />);
    const dot = container.querySelector(".ui-dot");
    expect(dot).not.toBeNull();
    expect(dot?.className).toBe("ui-dot");
  });

  it("pulse prop'u ile ui-dot--pulse ekler", () => {
    const { container } = render(<StatusDot tone="red" pulse />);
    expect(container.querySelector(".ui-dot")).toHaveClass("ui-dot--red", "ui-dot--pulse");
  });
});
