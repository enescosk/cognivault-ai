# Cogni Klinik — telefonda çalıştırma

## Expo Go ile hızlı cihaz testi

1. Telefona **Expo Go** yükle ve telefonla bilgisayarı aynı Wi-Fi'a bağla.
2. Bir terminalde backend'i başlat:

   ```bash
   ./scripts/run_backend.sh
   ```

3. İkinci terminalde telefon modunu başlat:

   ```bash
   ./scripts/run_mobile_phone.sh
   ```

4. Terminalde çıkan QR kodu Expo Go ile tara.

Demo kişisel hekim hesabı:

- E-posta: `hekim@cognivault.com`
- Şifre: `demo123`

Telefon bilgisayara erişemiyorsa macOS güvenlik duvarında Node ve Python için yerel ağ
erişimine izin ver. Otomatik bulunan IP yanlışsa komutu şöyle çalıştır:

```bash
COGNIVAULT_LAN_IP=192.168.1.25 ./scripts/run_mobile_phone.sh
```

## Bağımsız uygulama paketi

Expo Go geliştirme/test içindir. iPhone'a APK değil, imzalı IPA yüklenir.

### iPhone'a doğrudan kurulum (Ad Hoc IPA)

Gerekenler: Expo hesabı, ücretli Apple Developer Program üyeliği ve kurulacak iPhone'un
UDID kaydı. İlk yerel ağ paketi mevcut Mac backend'ine (`192.168.1.88:8000`) bağlanır.

```bash
cd mobile
npx eas-cli@latest login
npx eas-cli@latest build:configure
npx eas-cli@latest device:create
npx eas-cli@latest build --platform ios --profile iphone-local
```

Build tamamlanınca EAS'in verdiği kurulum bağlantısını iPhone'da açıp uygulamayı yükle.
Wi-Fi/LAN IP değişirse `eas.json` içindeki `EXPO_PUBLIC_API_URL` güncellenerek yeniden
build alınmalıdır.

### TestFlight

Kalıcı ve kolay güncellenebilir dağıtım için `production` build alıp App Store Connect'e
gönder:

```bash
npx eas-cli@latest build --platform ios --profile production
npx eas-cli@latest submit --platform ios --latest
```

Her iki iPhone yolu da Apple Developer Program üyeliği gerektirir. Ücretsiz Apple ID ile
yalnızca Mac'e kabloyla bağlı kişisel cihaza Xcode üzerinden kısa ömürlü geliştirme
kurulumu yapılabilir; paylaşılabilir bağımsız IPA üretilemez.
