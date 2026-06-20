// Vitest global setup: jest-dom matcher'larını (toBeInTheDocument, toHaveClass…)
// vitest expect'ine bağlar ve her testten sonra DOM'u temizler.
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
