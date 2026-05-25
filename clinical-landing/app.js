const scenarios = {
  pain: {
    intent: "Endodonti · priority",
    patient: "Arka dişim zonkluyor, yarın randevu var mı?",
    ai:
      "Şikayetinizi Endodonti için öncelikli randevu talebi olarak not aldım. Yarın hangi saat aralığı size uygun?",
    routing: "Doktor onayı: ağrı artışı sorusu eklendi",
  },
  gum: {
    intent: "Periodontoloji · review",
    patient: "Diş etim fırçalarken kanıyor, ne yapmalıyım?",
    ai:
      "Diş eti şikayetinizi Periodontoloji için not aldım. Kanama ne zamandır sürüyor ve randevu için hangi gün uygunsunuz?",
    routing: "Guardrail: tedavi tavsiyesi yok, randevu intake sorusu var",
  },
  child: {
    intent: "Pedodonti · child intake",
    patient: "Çocuğumun dolgusu düştü, bugün bakabilir misiniz?",
    ai:
      "Çocuk hasta için Pedodonti randevusu açabiliriz. Çocuğun yaşı, ağrı durumu ve uygun saat aralığını paylaşır mısınız?",
    routing: "Veli bilgisi ve çocuk hekimi slotu gerekiyor",
  },
  emergency: {
    intent: "Emergency · human handoff",
    patient: "Yüzüm şişti, yutkunmakta zorlanıyorum.",
    ai:
      "Bu durum acil olabilir. Lütfen 112'yi arayın veya en yakın acil servise başvurun. Klinik ekibine insan onayı için not düşüyorum.",
    routing: "Auto-send kapalı: doktor ve operatör onayı zorunlu",
  },
};

const tabs = document.querySelectorAll(".scenario-tab");
const patientText = document.querySelector("#patientText");
const aiText = document.querySelector("#aiText");
const scenarioIntent = document.querySelector("#scenarioIntent");
const routingText = document.querySelector("#routingText");

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const key = tab.dataset.scenario;
    const scenario = scenarios[key];
    if (!scenario) return;

    tabs.forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    scenarioIntent.textContent = scenario.intent;
    patientText.textContent = scenario.patient;
    aiText.textContent = scenario.ai;
    routingText.textContent = scenario.routing;
  });
});

const locationRange = document.querySelector("#locationRange");
const minuteRange = document.querySelector("#minuteRange");
const priceOutput = document.querySelector("#priceOutput");
const planOutput = document.querySelector("#planOutput");
const toggles = document.querySelectorAll(".toggle");

function formatTry(value) {
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency: "TRY",
    maximumFractionDigits: 0,
  }).format(value);
}

function updatePlan() {
  const locations = Number(locationRange.value);
  const minutes = Number(minuteRange.value);
  const activeAddons = [...toggles].filter((toggle) => toggle.classList.contains("active"));
  const base = 9500;
  const locationCost = locations * 3200;
  const minuteCost = Math.max(0, minutes - 1500) * 2.1;
  const addonCost = activeAddons.length * 1800;
  const estimate = Math.round((base + locationCost + minuteCost + addonCost) / 100) * 100;
  const labels = activeAddons.map((toggle) => toggle.textContent.trim()).join(" + ") || "Temel intake";

  priceOutput.textContent = formatTry(estimate);
  planOutput.textContent = `${locations} şube · ${minutes.toLocaleString("tr-TR")} dakika · ${labels}`;
}

locationRange.addEventListener("input", updatePlan);
minuteRange.addEventListener("input", updatePlan);
toggles.forEach((toggle) => {
  toggle.addEventListener("click", () => {
    toggle.classList.toggle("active");
    updatePlan();
  });
});
updatePlan();

document.querySelector(".demo-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  button.textContent = "Demo talebi alındı";
  button.disabled = true;
});
