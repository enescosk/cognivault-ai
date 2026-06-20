import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";

import { ToastContainer, showToast } from "../Toast";

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    // Bekleyen 4sn timer'ları gerçek timer'a dönerken at — unmount sonrası setState yok.
    vi.useRealTimers();
  });

  it("hiç toast yokken null render eder", () => {
    const { container } = render(<ToastContainer />);
    expect(container.firstChild).toBeNull();
  });

  it("showToast ile gönderilen mesajı role=status olarak gösterir", () => {
    render(<ToastContainer />);
    act(() => {
      showToast("Kaydedildi", "success");
    });
    const toast = screen.getByRole("status");
    expect(toast).toHaveClass("toast", "toast-success");
    expect(toast).toHaveTextContent("Kaydedildi");
  });

  it("tipine göre ikon gösterir ve birden çok toast biriktirir", () => {
    const { container } = render(<ToastContainer />);
    act(() => {
      showToast("Hata oldu", "error");
    });
    expect(container.querySelector(".toast-icon")).toHaveTextContent("✕");
    act(() => {
      showToast("Bilgi", "info");
    });
    expect(container.querySelectorAll(".toast")).toHaveLength(2);
  });

  it("4 saniye sonra otomatik kapanır", () => {
    render(<ToastContainer />);
    act(() => {
      showToast("Geçici", "info");
    });
    expect(screen.getByText("Geçici")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(screen.queryByText("Geçici")).toBeNull();
  });

  it("kapat butonuna basınca toast'ı hemen kaldırır", () => {
    render(<ToastContainer />);
    act(() => {
      showToast("Kapat beni", "error");
    });
    fireEvent.click(screen.getByLabelText("Bildirimi kapat"));
    expect(screen.queryByText("Kapat beni")).toBeNull();
  });
});
