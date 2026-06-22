import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ErrorBoundary } from "../ErrorBoundary";

function Boom(): never {
  throw new Error("panik");
}

describe("ErrorBoundary", () => {
  it("hata yoksa children'ı olduğu gibi render eder", () => {
    render(
      <ErrorBoundary>
        <div>sağlıklı içerik</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("sağlıklı içerik")).toBeInTheDocument();
  });

  it("children patlayınca varsayılan fallback'i scope ve hata mesajıyla gösterir", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary scope="Operatör paneli">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/Bir şeyler yanlış gitti/)).toHaveTextContent("Operatör paneli");
    expect(screen.getByText("panik")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tekrar dene" })).toBeInTheDocument();
    spy.mockRestore();
  });

  it("custom fallback verilirse varsayılan kart yerine onu gösterir", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary fallback={<div>özel hata ekranı</div>}>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("özel hata ekranı")).toBeInTheDocument();
    expect(screen.queryByText(/Bir şeyler yanlış gitti/)).toBeNull();
    spy.mockRestore();
  });

  it("'Tekrar dene' state'i sıfırlar ve düzelen child'ı yeniden render eder", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    let shouldThrow = true;
    function Toggle() {
      if (shouldThrow) throw new Error("ilk hata");
      return <div>kurtuldu</div>;
    }
    render(
      <ErrorBoundary>
        <Toggle />
      </ErrorBoundary>,
    );
    expect(screen.getByText("ilk hata")).toBeInTheDocument();
    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: "Tekrar dene" }));
    expect(screen.getByText("kurtuldu")).toBeInTheDocument();
    spy.mockRestore();
  });
});
