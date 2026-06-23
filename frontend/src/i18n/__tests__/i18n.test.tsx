import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";

import { I18nProvider, useT, fill } from "../index";
import { DICT } from "../dict";

const wrapper = ({ children }: { children: ReactNode }) => <I18nProvider>{children}</I18nProvider>;

describe("fill", () => {
  it("tek placeholder'ı değiştirir", () => {
    expect(fill("Merhaba {name}", { name: "Efe" })).toBe("Merhaba Efe");
  });

  it("sayıları ve birden çok değişkeni destekler", () => {
    expect(fill("v{version} · {dept}", { version: 3, dept: "Ortodonti" })).toBe("v3 · Ortodonti");
  });

  it("bilinmeyen placeholder'ı olduğu gibi bırakır", () => {
    expect(fill("{a}-{b}", { a: "1" })).toBe("1-{b}");
  });
});

describe("useT", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("provider dışında kullanılırsa açık bir hata fırlatır", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useT())).toThrow(/I18nProvider/);
    spy.mockRestore();
  });

  it("locale'i tr/en arasında değiştirir ve doğru çeviriyi döner", () => {
    const { result } = renderHook(() => useT(), { wrapper });
    act(() => result.current.setLocale("tr"));
    expect(result.current.t("nav.appointments")).toBe("Randevular");
    act(() => result.current.setLocale("en"));
    expect(result.current.t("nav.appointments")).toBe("Appointments");
  });

  it("setLocale seçimi localStorage'a kaydeder", () => {
    const { result } = renderHook(() => useT(), { wrapper });
    act(() => result.current.setLocale("en"));
    expect(localStorage.getItem("cognivault_locale")).toBe("en");
  });

  it("başlangıç locale'ini localStorage'dan okur", () => {
    localStorage.setItem("cognivault_locale", "en");
    const { result } = renderHook(() => useT(), { wrapper });
    expect(result.current.locale).toBe("en");
  });

  it("bilinmeyen anahtar için fallback parametresini döner", () => {
    const { result } = renderHook(() => useT(), { wrapper });
    expect(result.current.t("yok.boyle.anahtar", "yedek metin")).toBe("yedek metin");
  });

  it("fallback yoksa anahtarın kendisini döner (geliştirmede görünür kalsın diye)", () => {
    const { result } = renderHook(() => useT(), { wrapper });
    expect(result.current.t("tamamen.bilinmeyen")).toBe("tamamen.bilinmeyen");
  });
});

describe("sözlük paritesi", () => {
  it("tr ve en birebir aynı anahtar kümesine sahip (eksik çeviri yok)", () => {
    const tr = Object.keys(DICT.tr).sort();
    const en = Object.keys(DICT.en).sort();
    expect(en).toEqual(tr);
  });

  it("her iki dilde de boş string çeviri yok", () => {
    for (const locale of ["tr", "en"] as const) {
      for (const [key, value] of Object.entries(DICT[locale])) {
        expect(value, `${locale}.${key} boş olmamalı`).not.toBe("");
      }
    }
  });
});
