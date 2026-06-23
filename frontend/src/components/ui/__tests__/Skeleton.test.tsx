import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { Skeleton, SkeletonText, SkeletonBlock } from "../Skeleton";

describe("Skeleton", () => {
  it("skeleton sınıfını, aria-hidden ve inline width/height'ı uygular", () => {
    const { container } = render(<Skeleton width="120px" height="14px" />);
    const el = container.querySelector(".skeleton") as HTMLElement;
    expect(el).not.toBeNull();
    expect(el).toHaveAttribute("aria-hidden", "true");
    expect(el.style.width).toBe("120px");
    expect(el.style.height).toBe("14px");
  });

  it("ekstra className'i birleştirir", () => {
    const { container } = render(<Skeleton className="yuvarlak" />);
    expect(container.querySelector(".skeleton")).toHaveClass("skeleton", "yuvarlak");
  });
});

describe("SkeletonText", () => {
  it("varsayılan 3 satır, son satır %60 genişlikte render eder", () => {
    const { container } = render(<SkeletonText />);
    const lines = container.querySelectorAll(".skeleton");
    expect(lines).toHaveLength(3);
    expect((lines[2] as HTMLElement).style.width).toBe("60%");
    expect((lines[0] as HTMLElement).style.width).toBe("100%");
  });

  it("lines prop'una göre satır sayısını ayarlar", () => {
    const { container } = render(<SkeletonText lines={5} />);
    expect(container.querySelectorAll(".skeleton")).toHaveLength(5);
  });
});

describe("SkeletonBlock", () => {
  it("count kadar blok render eder", () => {
    const { container } = render(<SkeletonBlock count={4} />);
    const blocks = container.querySelectorAll(".skeleton.skeleton-block");
    expect(blocks).toHaveLength(4);
  });
});
