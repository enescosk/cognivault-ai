import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Test çalıştırması Vite ile aynı React transform'unu kullanır. Birim testleri
// davranış + sınıf bileşimi seviyesinde; CSS işlenmez (token'lar canlı preview'da doğrulanır).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: [
        "src/components/ui/**",
        "src/i18n/**",
        "src/components/ErrorBoundary.tsx",
      ],
    },
  },
});
