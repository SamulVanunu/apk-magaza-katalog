# APK Mağaza Kataloğu

Android TV / Android APK'ları için statik katalog + otomatik inbox işleme + tarayıcıdan yönetim paneli.

## Yapı

```
catalog.json                 Katalog (sürümler en yeni üstte)
apk/                         APK dosyaları
icons/                       Uygulama ikonları
inbox/                       Yüklenecek APK'lar ve .json yan dosyaları
tools/process_inbox.py       İşleyici (GitHub Actions)
.github/workflows/catalog.yml  Tetikleyici workflow
admin/index.html             Yönetici paneli (GitHub Pages)
```

Ham dosya kökü: `https://raw.githubusercontent.com/SamulVanunu/apk-magaza-katalog/main/`

## APK ekleme

### Panelden (önerilen)

1. Aşağıdaki jetonu oluşturun ve panelde giriş yapın.
2. **APK yükle** kartından dosyayı seçin; isteğe bağlı ad/kategori/açıklama/sürüm notu/TV bayraklarını doldurun.
3. **Yükle ve işlet** düğmesi APK'yı `inbox/<ad>.apk`, bilgileri `inbox/<ad>.json` olarak yazar ve workflow'u izler.
4. İşlem başarılıysa katalog otomatik yenilenir. Aynı sürüm (eşit/küçük `versionCode`) yüklenirse workflow kırmızı biter ve gerekçe iş özetinde görünür.

### Büyük APK'lar (GitHub Release)

Panelin Git Data API yolu yaklaşık **100 MB** üzerindeki dosyalarda GitHub tarafından reddedilir (137 MB'lık istek gövdesi `401 Bad credentials` döner). Bu durumda Release kullanın:

1. GitHub → **Releases → Draft a new release**. Tag oluşturun (ör. `inbox-andrei-1.4.4`), başlık verin.
2. **Notes** alanına meta veri JSON'u koyun (boş bırakılabilir):
   ```json
   {"name":"ANDREI","category":"Video","shortDescription":"...","description":"...","notes":"...","screenshots":[],"tvSupported":false,"tvOnly":false}
   ```
3. APK dosyasını **Attach binaries** ile ekleyip **Publish release** yapın.
4. `release: [published]` tetikleyicisi asset'i `inbox/`'a indirir, işleyici `apk/`'a taşıyıp kataloğu günceller. Katalog `apkUrl` adresi yine `raw.githubusercontent.com` olur.

İşlem başarısız olursa `Actions` sekmesinden **Run workflow** (`workflow_dispatch`) ile en son Release asset'i yeniden denenebilir.

### Manuel

APK'yı `inbox/` içine koyup `main` dalına push edin. İsteğe bağlı yan dosya `inbox/<ad>.json`:

```json
{
  "name": "Uygulama Adı",
  "category": "Araçlar",
  "shortDescription": "Kısa açıklama",
  "description": "Uzun açıklama",
  "notes": "Sürüm notu",
  "screenshots": ["https://raw.githubusercontent.com/.../ss1.png"],
  "tvSupported": true,
  "tvOnly": false
}
```

## Fine-grained PAT oluşturma

1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Token name: `apk-katalog-admin`. Expiration: uygun süre.
3. Resource owner: `SamulVanunu`. Repository access: **Only select repositories** → `apk-magaza-katalog`.
4. Permissions → Repository permissions → **Contents: Read and write**. (Actions iznine gerek yok; workflow durumunu okumak için `Actions: Read-only` verebilirsiniz.)
5. **Generate token** → jetonu kopyalayın. Jeton yalnızca panelin `localStorage` alanına kaydedilir; depoya, URL'ye veya loglara yazılmaz. **Çıkış** ile silinir.

> Depo herkese açıktır. Keystore, `google-services.json`, API anahtarı, parola veya classic PAT **asla** eklemeyin.

## Panel özellikleri

- Giriş/Çıkış (jeton doğrulaması ve `Contents: write` kontrolü)
- Katalog kartları, sürüm geçmişi ve TV rozetleri
- APK yükleme (Git Data API ile büyük dosya blob'u) + canlı workflow durumu
- Uygulama/sürüm düzenleme, SHA çakışmasında yenileme uyarısı
- Onaylı sürüm/uygulama silme, APK silme için ayrı onay
- Şema doğrulama + sağlık kontrolü (ham URL 200 ve SHA-256 eşleşmesi)
- Koyu/açık tema, 48px+ dokunma hedefleri, telefon öncelikli düzen

Panel yalnızca `api.github.com` ve `raw.githubusercontent.com` adreslerine istek atar; harici CDN/betik kullanmaz; CSP meta etiketi vardır.

## Doğrulama

İşleyici, kataloğa yazmadan önce şunları kontrol eder: geçerli JSON, ham URL kökü, 64 haneli küçük hex `sha256`/`signerSha256`, gerçek bayt boyutu, azalan `versionCode` sırası, `updatedAt` = bugün. Hata varsa `catalog.json` değişmez, workflow başarısız olur ve neden `$GITHUB_STEP_SUMMARY` içine yazılır.
