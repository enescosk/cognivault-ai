import { describe, expect, it } from "vitest";

import { splitSpeechChunks } from "../patient/PatientChatRoom";

describe("splitSpeechChunks", () => {
  it("kısa metni tek parça döndürür", () => {
    expect(splitSpeechChunks("Merhaba, size nasıl yardımcı olabilirim?")).toEqual([
      "Merhaba, size nasıl yardımcı olabilirim?",
    ]);
  });

  it("uzun yanıtı cümle sınırlarından böler", () => {
    const text =
      "Geçmiş olsun, hemen ilgilenelim ve dişinizi kontrol edelim. " +
      "Yarın için müsait saatlerimiz dokuz otuz, on dört ve on altı. " +
      "Hangisinde randevu oluşturmamı istersiniz?";
    const chunks = splitSpeechChunks(text);
    expect(chunks.length).toBeGreaterThan(1);
    // Parçalar birleşince orijinal metni (boşluk normalize) verir — kayıp yok.
    expect(chunks.join(" ")).toBe(text);
    // Her parça bir cümle sonuyla biter (son parça hariç zorunlu değil).
    for (const c of chunks.slice(0, -1)) {
      expect(c).toMatch(/[.!?…]$/);
    }
  });

  it("çok kısa cümleleri bir sonrakiyle birleştirir", () => {
    const chunks = splitSpeechChunks("Tamam. Peki. Randevunuzu yarın saat ondaki boşluğa alıyorum, onay mesajı göndereceğim.");
    // "Tamam." ve "Peki." tek başına parça olmamalı (min uzunluk altı).
    expect(chunks[0]).toContain("Tamam. Peki.");
  });

  it("noktalama olmayan metinde de çalışır", () => {
    expect(splitSpeechChunks("randevu almak istiyorum")).toEqual(["randevu almak istiyorum"]);
  });

  it("boş/boşluk metinde boş dizi döndürür", () => {
    expect(splitSpeechChunks("   ")).toEqual([]);
  });

  it("fazla boşlukları normalize eder", () => {
    const chunks = splitSpeechChunks("Birinci  cümle   burada bitiyor.    İkinci cümle de yeterince uzun olsun diye uzatıldı.");
    expect(chunks.every((c) => !c.includes("  "))).toBe(true);
  });
});
