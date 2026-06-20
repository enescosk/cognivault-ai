import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { Button } from "../Button";

describe("Button", () => {
  it("varsayılan olarak ghost variant + md boyutla render eder", () => {
    render(<Button>Tıkla</Button>);
    const btn = screen.getByRole("button", { name: "Tıkla" });
    expect(btn).toHaveClass("ui-btn", "ui-btn--ghost");
    // md boyutta ekstra boyut sınıfı yok
    expect(btn.className).not.toMatch(/ui-btn--(sm|lg)/);
  });

  it.each([
    ["primary", "ui-btn--primary"],
    ["ghost", "ui-btn--ghost"],
    ["subtle", "ui-btn--subtle"],
    ["danger", "ui-btn--danger"],
  ] as const)("%s variantı için %s sınıfını uygular", (variant, cls) => {
    render(<Button variant={variant}>x</Button>);
    expect(screen.getByRole("button")).toHaveClass(cls);
  });

  it("sm ve lg boyut sınıflarını uygular", () => {
    const { rerender } = render(<Button size="sm">x</Button>);
    expect(screen.getByRole("button")).toHaveClass("ui-btn--sm");
    rerender(<Button size="lg">x</Button>);
    expect(screen.getByRole("button")).toHaveClass("ui-btn--lg");
  });

  it("block prop'u ile tam genişlik sınıfı ekler", () => {
    render(<Button block>x</Button>);
    expect(screen.getByRole("button")).toHaveClass("ui-btn--block");
  });

  it("dışarıdan gelen className'i token sınıflarıyla birleştirir", () => {
    render(<Button className="özel-sınıf">x</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("ui-btn", "özel-sınıf");
  });

  it("onClick handler'ını çağırır", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>x</Button>);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("disabled iken tıklamayı tetiklemez ve type'ı geçirir", () => {
    const onClick = vi.fn();
    render(
      <Button disabled type="submit" onClick={onClick}>
        x
      </Button>,
    );
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("type", "submit");
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });
});
