# Statik JSON (1. faz: panel + site.json) Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anasayfa, kategoriler ve hakkımızda verilerini `site.json` olarak depoya yazan ve panelden düzenlenebilen bir akış kurmak; uygulama içerikleri `catalog.json`'da kalmaya devam etmek.

**Architecture:** Mevcut `apk-magaza-katalog` deposunda `catalog.json` yanına `site.json` eklenir. Yönetici paneli (tek HTML, gömülü JS) dosyayı ham URL'den okur, şema doğrulaması yapar ve mevcut Git Data API yardımcısı (`commitFiles`) ile tek commit'te yazar. Uygulama tarafındaki değişiklikler bu planın dışında, 2. fazda yapılır.

**Tech Stack:** Tek HTML + gömülü JS/CSP, GitHub REST + Git Data API, Node `assert` (test), Playwright + Chrome (DOM test), Python 3 (yardımcı doğrulama).

**Spec:** `design/specs/2026-11-25-static-json-design.md`

## Global Constraints

- Panel tek HTML dosyasıdır: `admin/index.html`; harici betik/CDN yok; CSP meta etiketi korunur.
- Yayınlanan kopya `docs/admin/index.html` ile **birebir özdeş** olmalı; her değişiklikten sonra `cmp` ile doğrulanır.
- Jeton yalnızca `localStorage` anahtarı `apk-magaza-pat` içinde; depoya, loglara, URL'ye yazılmaz; Çıkış ile silinir.
- `catalog.json` şeması (`catalogVersion`, `apps[]`, `versions[]`) değiştirilmez.
- `site.json` şeması: `siteVersion: 1`, `updatedAt: YYYY-MM-DD`, `home.headline`, `home.defaultSort ∈ {popular,new}`, `categories: string[]` (boş olamaz, "Tümü" içeremez, tekrarsız), `about.title/description/versionLabel` (boş olamaz).
- Arayüz Türkçe; dokunma hedefleri ≥48px; koyu/açık tema korunur.
- Ham dosya kökü: `https://raw.githubusercontent.com/SamulVanunu/apk-magaza-katalog/main/`.

## Review Focus

- `site.json` henüz yoksa (404) panel çökmesin; "Site verileri yok, örnek değerlerle başlayın" durumu görünsün. → Task 3, adım 4.
- Bozuk/şemaya uymayan JSON commit edilmesin; hata mesajı hangi alanın hatalı olduğunu söylesin. → Task 2 + Task 3, adım 5.
- Kullanıcı kategorilere "Tümü" yazarsa reddedilsin (mevcut kodda bu ayrı bir sabit çip). → Task 2, adım 2.
- Eşzamanlı değişiklikte ref güncellemesi 409 dönerse panel "yenileyip tekrar dene" mesajı göstersin. → Task 3, adım 6.
- `docs/admin` kopyası kaybolursa panel güncel olmayan sürümü yayınlamasın. → Task 3, adım 7.

---

### Task 1: `site.json` dosyasını tohumla

**Files:**
- Create: `site.json`
- Test: `tests/site-json.test.js`

**Interfaces:**
- Consumes: yok.
- Produces: panelin okuyacağı `site.json`; testin doğruladığı sabit değerler.

- [ ] **Step 1: Başarısız testi yaz**

`tests/site-json.test.js` içinde `node:assert` ile: dosyanın JSON olarak ayrıştırıldığını; `siteVersion === 1`; `updatedAt`'in `/^\d{4}-\d{2}-\d{2}$/` ile eşleştiğini; `home.defaultSort`'un `popular` veya `new` olduğunu; `categories.length > 0`, `!categories.includes("Tümü")`, `new Set(categories).size === categories.length` olduğunu; `about.title/description/versionLabel` alanlarının boş olmadığını doğrula.

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `node tests/site-json.test.js`
Expected: `ENOENT: no such file or directory, open 'site.json'`

- [ ] **Step 3: `site.json` dosyasını oluştur**

Tasarım şemasına uy, değerleri mevcut arayüzden tohumla: `headline: "Uygulamanı keşfet."`, `defaultSort: "popular"`, `categories: ["Araçlar", "Video"]`, `about.title: "Uygulama hakkında"`, `about.description: "Uygulama kataloğu, indirme ve TV yönetimi."`, `about.versionLabel: "Sürüm %1$s"`, `updatedAt` bugünün tarihi.

- [ ] **Step 4: Testin geçtiğini gör**

Run: `node tests/site-json.test.js`
Expected: çıkış 0, "site.json OK".

- [ ] **Step 5: Commit**

```bash
git add site.json tests/site-json.test.js
git commit -m "site.json: statik site verileri için şema ve tohum değerler"
```

---

### Task 2: Panelde `validateSite()` doğrulayıcısı

**Files:**
- Modify: `admin/index.html` (gömülü `<script>` bloğu)
- Test: `tests/site-validation.test.js`

**Interfaces:**
- Consumes: yok (salt fonksiyon).
- Produces: `validateSite(data) -> string[]` — geçerliyse boş dizi, hatalıysa Türkçe hata mesajları. Task 3 ve 4 bunu kullanır.

- [ ] **Step 1: Başarısız testi yaz**

`tests/site-validation.test.js`: HTML'den `validateSite` satırını regex ile çıkarıp `eval` ile al; şunları doğrula:
  - geçerli tohum veri → `[]`;
  - `siteVersion: 2` → "siteVersion 1 olmalı" içeren mesaj;
  - `updatedAt: "25-11-2026"` → tarih mesajı;
  - `categories: []` → kategori mesajı;
  - `categories: ["Araçlar","Araçlar"]` → tekrar mesajı;
  - `categories: ["Tümü"]` → "Tümü" mesajı;
  - `home.defaultSort: "latest"` → sıralama mesajı;
  - `about.description: ""` → hakkımızda mesajı.

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `node tests/site-validation.test.js`
Expected: `validateSite is not defined` veya regex eşleşmedi.

- [ ] **Step 3: `validateSite(data)` fonksiyonunu gömülü JS'e ekle**

İmza: `function validateSite(data){ ... return errors; }`. Kurallar Global Constraints'teki şema ile aynı; her hata Türkçe ve alan adını içerir.

- [ ] **Step 4: Testin geçtiğini gör**

Run: `node tests/site-validation.test.js`
Expected: çıkış 0, "validateSite OK".

- [ ] **Step 5: Commit**

```bash
git add admin/index.html tests/site-validation.test.js
git commit -m "Panel: site.json şema doğrulayıcısı"
```

---

### Task 3: Panelde Site verileri kartı, okuma ve kaydetme

**Files:**
- Modify: `admin/index.html` (HTML + gömülü JS)
- Modify: `docs/admin/index.html` (birebir kopya)
- Test: `tests/test_panel_site.py` (Playwright)

**Interfaces:**
- Consumes: `validateSite(data)` (Task 2), `msg(el,text,kind)`, `commitFiles(files,message)`, `BASE_URL`/`RAW` sabitleri, `baseSha` (mevcut panel değişkeni).
- Produces: `siteData` (modül seviyesi nesne), `loadSite() -> Promise<void>`, `saveSite() -> Promise<void>`; alan kimlikleri `siteHeadline`, `siteDefaultSort`, `siteCategories`, `siteAboutTitle`, `siteAboutDescription`, `siteAboutVersion`.

- [ ] **Step 1: Başarısız DOM testi yaz**

`tests/test_panel_site.py`: `python -m http.server` ile `admin/` klasörünü yerel sun; Playwright/Chrome ile sayfayı aç; `raw.githubusercontent.com/**/site.json` isteğini gerçek `site.json` içeriğiyle `route.fulfill` et; `api.github.com/**` isteklerini kaydet. Şunları doğrula: kart başlığı "Site verileri" görünüyor; alanlar tohum değerlerle dolu; bir alanı değiştirip "Site verilerini kaydet" düğmesine basınca `api.github.com/.../git/blobs` isteği gidiyor ve `git/trees` isteğinin gövdesinde `path: "site.json"` var; `git/refs` PATCH gövdesi `force: false`.

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `python tests/test_panel_site.py`
Expected: `TimeoutError` / "Site verileri" bulunamadı.

- [ ] **Step 3: HTML kartını ve JS akışını ekle**

Sağ sütundaki "APK yükle" kartının üstüne "Site verileri" kartını koy: başlık, varsayılan sıralama (`select`), kategoriler (virgülle), hakkımızda başlığı/açıklama/sürüm etiketi, "Site verilerini kaydet" düğmesi, sonuç mesajı alanı. JS: `siteData` değişkeni; `loadSite()` ham URL'den `?t=Date.now()` ile oku, `JSON.parse`, `validateSite` ile doğrula, alanları doldur; `saveSite()` formdan nesne kur, doğrula, `commitFiles([{path:"site.json", text: JSON.stringify(siteData,null,2)+"\n"}], "site: güncelle")` çağır, sonra `loadSite()`.

- [ ] **Step 4: 404/boş dosya durumunu ekle**

`loadSite()` içinde `r.status === 404` ise alanları boş bırak ve mesaj alanına "Site verileri henüz yok; örnek değerlerle başlayın." yaz; diğer hatalarda mesajı göster. Teste 404 senaryosunu da ekle (kartın görünür ve mesajın doğru olduğunu doğrula).

- [ ] **Step 5: Hata mesajlarını doğrula**

Geçersiz kategori ("Tümü") girildiğinde hiçbir API isteği gönderilmediğini ve mesajın "Tümü" içerdiğini doğrula; eşzamanlı değişiklikte `PATCH /git/refs` 409 dönerse mesajın "yenileyip tekrar" içerdiğini doğrula (route ile 409 taklidi).

- [ ] **Step 6: Testlerin geçtiğini gör**

Run: `python tests/test_panel_site.py`
Expected: çıkış 0.

- [ ] **Step 7: Yayın kopyasını eşitle ve doğrula**

Run: `cp admin/index.html docs/admin/index.html && cmp admin/index.html docs/admin/index.html`
Expected: `cmp` çıkış 0.

- [ ] **Step 8: Commit**

```bash
git add admin/index.html docs/admin/index.html tests/test_panel_site.py
git commit -m "Panel: site.json düzenleme ve kaydetme akışı"
```

---

### Task 4: Doğrulama paneline site.json kontrolünü ekle

**Files:**
- Modify: `admin/index.html`
- Modify: `docs/admin/index.html`
- Test: `tests/site-validation.test.js` (genişletildi)

**Interfaces:**
- Consumes: `siteData`, `validateSite(data)` (Task 2/3), `msg`, `RAW`.
- Produces: "Şema kontrolü" ve "Sağlık kontrolü" düğmelerinin `site.json`'u da kapsaması.

- [ ] **Step 1: Başarısız testi genişlet**

`tests/site-validation.test.js` içine: doğrulama panelinin `siteData` için `validateSite` sonuçlarını mesaja eklediğini; sağlık kontrolünün `RAW + "site.json?t=..."` adresine istek attığını ve HTTP 200/'değil' mesajını ürettiğini doğrulayan DOM testleri ekle (Playwright veya Node + mock).

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `python tests/test_panel_site.py` veya `node tests/site-validation.test.js`
Expected: site.json satırı mesajda yok.

- [ ] **Step 3: Şema ve sağlık kontrolünü genişlet**

`validateBtn` içinde `siteData` varsa `validateSite(siteData)` sonuçlarını katalog hatalarına ekle; yoksa "site.json yüklenmedi" uyarısı ver. `healthBtn` içinde site.json için ayrıca `fetch(RAW+"site.json?t="+Date.now())` yapıp durum ve JSON geçerliliğini mesaja ekle; mevcut APK hash kontrolü aynen kalsın.

- [ ] **Step 4: Testlerin geçtiğini gör**

Run: test komutu
Expected: çıkış 0; mesajda `site.json` satırı var.

- [ ] **Step 5: Kopyayı eşitle, commit**

Run: `cp admin/index.html docs/admin/index.html && cmp admin/index.html docs/admin/index.html`, sonra:
```bash
git add admin/index.html docs/admin/index.html tests/site-validation.test.js
git commit -m "Panel doğrulaması: site.json şema ve sağlık kontrolü"
```

---

### Task 5: README ve canlı doğrulama

**Files:**
- Modify: `README.md`
- Test: el komutları

**Interfaces:**
- Consumes: Task 1–4 çıktıları.
- Produces: güncel kullanım dokümanı; canlı `site.json` doğrulaması.

- [ ] **Step 1: README'ye site.json bölümünü ekle**

"Yapı" listesine `site.json` satırı; yeni bir bölüm: alanların anlamı, panelden nasıl düzenleneceği, uygulamanın 2. fazda okuyacağı URL, `catalog.json`'un değişmediği notu.

- [ ] **Step 2: Canlı doğrulama**

Run: `curl -s -o /dev/null -w "%{http_code}" "https://raw.githubusercontent.com/SamulVanunu/apk-magaza-katalog/main/site.json?t=$(date +%s)"` ve `curl -s .../site.json | python -m json.tool >/dev/null`
Expected: `200`, JSON geçerli.

- [ ] **Step 3: Commit ve push**

```bash
git add README.md
git commit -m "README: site.json kullanımı"
git push origin main
```
