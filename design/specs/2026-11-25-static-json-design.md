# Statik verinin JSON'a taşınması — tasarım

Tarih: 2026-11-25
Durum: taslak — onay bekliyor

## Niyet ve neden

`cep depo` uygulamasındaki bazı ekranlar (ana sayfa, kategoriler, hakkımızda, uygulama içerikleri) sık değişmeyen veriler için canlı veritabanı okuması yapıyor. Amaç bu verileri statik JSON dosyalarına alıp belli aralıklarla güncellemek; böylece veritabanı işlemleri azalacak ve içerik yönetimi tek yerden (yönetici paneli + GitHub) yapılabilecek.

Yorumlar ve şikayetler gibi güncel olması gereken veriler **şimdilik canlı veritabanında (Firebase) kalacak**; bunların yeniden yapılandırılması ayrı, ikinci bir faz.

## Hedefler

1. Anasayfa, kategoriler, hakkımızda ve uygulama içerikleri JSON olarak yayınlanacak.
2. Yönetici paneli bu verileri düzenleyip tek bir commit ile depoya yazacak.
3. Uygulama, JSON'u HTTPS üzerinden okuyup doğrulayacak, önbelleğe alacak ve bozuk/erişilemez yanıtta son geçerli sürümü kullanacak.
4. Mevcut katalog şeması (`catalog.json`) ve mevcut uygulama davranışı korunacak.

## Hedef dışı

- Yorumlar, şikayetler, kullanıcı profilleri, oturumlar, bildirimler.
- Jeton, parola, API anahtarı veya herhangi bir gizli verinin JSON'a/uygulamaya konması.
- Katalog şemasının (`catalogVersion`, `apps[]`, `versions[]`) değiştirilmesi.

## Anti-hedefler

- Uygulamanın çevrimdışıyken boş/hatalı ekran göstermesi.
- Paneldeki bir düzenlemenin katalog dosyasını bozması.
- Eski uygulama sürümlerinin kataloğu okuyamaz hale gelmesi.

## Kısıtlar

- Depo herkese açık; dosyalar `raw.githubusercontent.com` üzerinden sunuluyor.
- Panel jetonu yalnızca tarayıcı `localStorage`'ında tutuyor; depoya yazılmıyor.
- Panel CSP'si yalnızca `api.github.com` ve `raw.githubusercontent.com` bağlantılarına izin veriyor.
- Uygulama Kotlin/Compose, `minSdk 24`; mevcut `CatalogRepository` HTTPS + doğrulama + önbellek deseni kullanıyor.
- Kategoriler şu an `catalog.apps[].category` değerlerinden türetiliyor; Hakkında metni `strings.xml` içinde sabit.

## Yaklaşımlar

1. **Mevcut depo + `site.json` (seçildi):** Anasayfa, kategoriler ve hakkımızda yeni bir `site.json` dosyasına; uygulama içerikleri mevcut `catalog.json`'da kalır. Uygulama iki HTTPS URL okur. Artıları: yeni repo/altyapı yok, mevcut katalog bozulmaz, dosya başına atomik commit. Eksileri: uygulamaya ikinci URL tanımı gerekir.
2. **Ayrı depo + ayrı dosyalar:** Statik veriler farklı bir depoda tutulur. İzin ayrımı olur ama iki farklı kaynaktan okuma, güncellemenin atomik olmaması ve ek repo yönetimi dezavantaj.
3. **Her şey `catalog.json` içinde:** Tek dosya, tek istek. Ancak mevcut şema ve uygulamadaki `parseAndValidateCatalog` değişir; eski sürümlerle uyumluluk riski.

## Seçilen tasarım

### Dosyalar

- `catalog.json` — olduğu gibi kalır (uygulama içerikleri ve sürümler).
- `site.json` — yeni; aşağıdaki şema.
- `docs/admin/index.html` (yayınlanan panel) ve `admin/index.html` (kaynak) — özdeş tutulur.

### `site.json` şeması

```json
{
  "siteVersion": 1,
  "updatedAt": "2026-11-25",
  "home": {
    "headline": "Uygulamanı keşfet.",
    "defaultSort": "popular",
    "tabs": ["popular", "new"]
  },
  "categories": ["Tümü", "Araçlar", "Video"],
  "about": {
    "title": "cep depo hakkında",
    "description": "Uygulama kataloğu, indirme ve TV yönetimi.",
    "versionLabel": "Sürüm %1$s"
  }
}
```

Doğrulama: `siteVersion == 1`; `updatedAt` geçerli `YYYY-MM-DD`; `categories` boş olmayan, tekrarsız dizgi dizisi; `home.defaultSort` `popular` veya `new`; `tabs` bu iki değerin alt kümesi; `about.*` boş olmayan dizgiler. Her dizgi alanı için makul uzunluk sınırı (ör. 500 karakter) uygulanır.

Kategori çipleri: `site.json` içindeki `categories` dizisi **temel alınır**; katalogda olup bu listede bulunmayan kategoriler listenin sonuna eklenir. Böylece yeni bir kategori, panel güncellenmeden de kaybolmaz.

### Panel tarafı

- `admin/index.html` içine **Site verileri** kartı eklenir: başlık, varsayılan sıralama, sekmeler, kategoriler (virgülle), hakkımızda başlığı/açıklama/sürüm etiketi.
- Mevcut `commitFiles()` yardımcısı kullanılarak `site.json` tek commit ile yazılır; `catalog.json` düzenleme akışı değiştirilmez.
- Paneldeki "Kataloğu yenile" akışı `site.json`'u da okur ve alanları doldurur; dosya yoksa boş/hata durumu açıkça gösterilir.
- Değişiklik sonrası `docs/admin/index.html` birebir kopyalanır (`cmp` ile doğrulanır).

### Uygulama tarafı

- `app/build.gradle.kts`: `SITE_JSON_URL` buildConfigField eklenir (`https://raw.githubusercontent.com/SamulVanunu/apk-magaza-katalog/main/site.json`).
- Yeni `SiteRepository.kt`: `fetchSite()` / `cachedSite()`; HTTPS zorunluluğu, HTTP 200..299 kontrolü, yukarıdaki şema doğrulaması, `SharedPreferences` önbelleği. `CatalogRepository` ile aynı hata deseni.
- `app/src/main/assets/site.sample.json`: çevrimdışı ilk açılış için örnek dosya.
- `StoreScreens.kt`: `HomeScreen` kategori çiplerini ve sıralama varsayılanını `site.json`'dan alır; Hakkında diyaloğu `site.about` değerlerini kullanır, eksik alanlarda `stringResource` değerine düşer.
- Ekran metinlerinin tamamı taşınmaz; yalnızca içerik niteliğindeki alanlar JSON'dan gelir, sabit UI etiketleri `strings.xml`'de kalır.

### Yenileme ve önbellek

- Uygulama açılışta önbelleği gösterir, arka planda `site.json` ve `catalog.json` için tek seferlik tazeleme yapar.
- Önbellek yaşı önerilen TTL: **6 saat** (builder kararı; değiştirilebilir). Kullanıcı yenileme simgesine bastığında TTL bakılmaksızın tazelenir.
- Bozuk JSON, 4xx/5xx veya ağ hatasında önbellek korunur; önbellek de yoksa `site.sample.json` kullanılır. Hata kullanıcıya gösterilmez (sessiz fallback).

### 2. faz (şimdi yapılmaz)

Yorumlar ve şikayetler `CommunityViewModel` / Firebase'de kalır. Bunların okuma/yazma akışının yeniden yapılandırılması için ayrı bir tasarım dokümanı ve ayrı uygulama planı yazılacak.

## Builder'a bırakılan kararlar

- TTL değeri (öneri: 6 saat) ve yenileme tetikleyicisi (açılış + manuel yenileme; WorkManager gerekirse eklenebilir).
- `site.sample.json` içindeki örnek değerlerin tam metni.
- Panel formundaki alan sırası ve mobil yerleşim ayrıntıları.

Bu kararlar ürün davranışını değiştirmediği için uygulama sırasında belirlenebilir.
