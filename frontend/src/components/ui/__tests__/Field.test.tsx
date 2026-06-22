import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { Field } from "../Field";

describe("Field", () => {
  it("label'ı input ile id üzerinden ilişkilendirir", () => {
    render(<Field label="E-posta" id="email" placeholder="ad@klinik.com" />);
    // getByLabelText, label htmlFor=id + input id=id eşleşmesini doğrular
    const input = screen.getByLabelText("E-posta");
    expect(input.tagName).toBe("INPUT");
    expect(input).toHaveAttribute("id", "email");
    expect(input).toHaveClass("ui-input");
    expect(input).toHaveAttribute("placeholder", "ad@klinik.com");
  });

  it("hint metnini render eder", () => {
    render(<Field label="Şifre" hint="En az 8 karakter" />);
    const hint = screen.getByText("En az 8 karakter");
    expect(hint).toHaveClass("ui-field-hint");
  });

  it("label ve hint verilmezse onları render etmez", () => {
    const { container } = render(<Field id="x" />);
    expect(container.querySelector(".ui-field-label")).toBeNull();
    expect(container.querySelector(".ui-field-hint")).toBeNull();
    expect(container.querySelector("input.ui-input")).not.toBeNull();
  });

  it("controlled input olarak onChange'i tetikler", () => {
    const onChange = vi.fn();
    render(<Field id="x" value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "merhaba" } });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("dışarıdan gelen className'i ui-input ile birleştirir", () => {
    render(<Field id="x" className="dar" />);
    expect(screen.getByRole("textbox")).toHaveClass("ui-input", "dar");
  });
});
