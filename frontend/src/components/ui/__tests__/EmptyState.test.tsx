import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { EmptyState } from "../EmptyState";

describe("EmptyState", () => {
  it("başlığı render eder", () => {
    render(<EmptyState title="Henüz randevu yok" />);
    expect(screen.getByRole("heading", { name: "Henüz randevu yok" })).toBeInTheDocument();
  });

  it("açıklamayı yalnız verildiğinde render eder", () => {
    const { rerender } = render(<EmptyState title="Boş" />);
    expect(screen.queryByText("Bir açıklama")).toBeNull();
    rerender(<EmptyState title="Boş" description="Bir açıklama" />);
    expect(screen.getByText("Bir açıklama")).toBeInTheDocument();
  });

  it("varsayılan ikonu gösterir", () => {
    render(<EmptyState title="x" />);
    expect(screen.getByText("📭")).toBeInTheDocument();
  });

  it("özel ikonu gösterir", () => {
    render(<EmptyState title="x" icon="🦷" />);
    expect(screen.getByText("🦷")).toBeInTheDocument();
  });

  it("action verildiğinde butonu render eder ve onClick'i çağırır", () => {
    const onClick = vi.fn();
    render(<EmptyState title="x" action={{ label: "Yenile", onClick }} />);
    const btn = screen.getByRole("button", { name: "Yenile" });
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("action yoksa buton render etmez", () => {
    render(<EmptyState title="x" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
