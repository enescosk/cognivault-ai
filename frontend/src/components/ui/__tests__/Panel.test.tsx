import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Panel } from "../Panel";

describe("Panel", () => {
  it("title, subtitle, actions, footer ve children'ı ilgili bölümlere yerleştirir", () => {
    const { container } = render(
      <Panel
        title="Onay kuyruğu"
        subtitle="3 bekleyen"
        actions={<button>Yenile</button>}
        footer={<span>son güncelleme</span>}
      >
        gövde içeriği
      </Panel>,
    );
    expect(container.querySelector(".ui-panel-title")).toHaveTextContent("Onay kuyruğu");
    expect(container.querySelector(".ui-panel-sub")).toHaveTextContent("3 bekleyen");
    expect(screen.getByRole("button", { name: "Yenile" })).toBeInTheDocument();
    expect(container.querySelector(".ui-panel-body")).toHaveTextContent("gövde içeriği");
    expect(container.querySelector(".ui-panel-foot")).toHaveTextContent("son güncelleme");
  });

  it("title/subtitle/actions yoksa header render etmez", () => {
    const { container } = render(<Panel>sadece gövde</Panel>);
    expect(container.querySelector(".ui-panel-head")).toBeNull();
    expect(container.querySelector(".ui-panel-body")).toHaveTextContent("sadece gövde");
  });

  it("yalnız subtitle verilse bile header'ı gösterir", () => {
    const { container } = render(<Panel subtitle="alt başlık">x</Panel>);
    expect(container.querySelector(".ui-panel-head")).not.toBeNull();
    expect(container.querySelector(".ui-panel-title")).toBeNull();
  });

  it("ekstra className'i ui-panel ile birleştirir", () => {
    const { container } = render(<Panel className="dar">x</Panel>);
    expect(container.querySelector(".ui-panel")).toHaveClass("ui-panel", "dar");
  });
});
