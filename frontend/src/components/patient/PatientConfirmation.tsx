import type { PublicClinicView } from "../../api/patientClient";

interface Props {
  clinic: PublicClinicView;
  onStartOver: () => void;
}

/**
 * Randevu kayıt sonrası onay ekranı.
 *
 * MVP: SMS gönderimi mock. Faz P3'te gerçek Netgsm/Twilio entegrasyonu.
 */
export function PatientConfirmation({ clinic, onStartOver }: Props) {
  return (
    <div className="patient-card patient-confirmation">
      <div className="patient-confirmation-check" aria-hidden>
        ✓
      </div>
      <h2>Randevu talebiniz oluşturuldu</h2>
      <p>
        {clinic.name} ekibi randevunuzu kısa süre içinde onaylayacak ve size SMS ile
        teyit gönderecek. SMS'i alıncaya kadar saatleri lütfen aramamızı bekleyin.
      </p>

      <ul className="patient-confirmation-next">
        <li>📩 Onay SMS'i — birkaç dakika içinde</li>
        <li>📞 Eğer detay gerekirse klinik sizi arayacak</li>
        <li>🛡 Konuşma kayıtları KVKK uyarınca 1 yıl içinde silinecek</li>
      </ul>

      {clinic.public_address ? (
        <p className="patient-hint">
          <strong>Adres:</strong> {clinic.public_address}
        </p>
      ) : null}
      {clinic.contact_phone ? (
        <p className="patient-hint">
          <strong>İletişim:</strong> {clinic.contact_phone}
        </p>
      ) : null}

      <button type="button" className="patient-cta" onClick={onStartOver}>
        Yeni bir görüşme başlat
      </button>
    </div>
  );
}
