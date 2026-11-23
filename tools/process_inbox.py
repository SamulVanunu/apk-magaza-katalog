#!/usr/bin/env python3
"""APK inbox isleyicisi.

inbox/*.apk dosyalarini okur, manifest bilgilerini cikarir, apk/ ve icons/
klasorlerine tasir ve catalog.json dosyasini gunceller.

Hata durumunda catalog.json'a YAZMAZ, nedeni GITHUB_STEP_SUMMARY'ye yazar
ve cikis kodu 1 ile workflow'u kirmizi bitirir.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from pyaxmlparser import APK
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyaxmlparser", "cryptography"],
        check=True,
    )
    from pyaxmlparser import APK

BASE_URL = "https://raw.githubusercontent.com/SamulVanunu/apk-magaza-katalog/main/"
INBOX_DIR = Path("inbox")
APK_DIR = Path("apk")
ICONS_DIR = Path("icons")
CATALOG_FILE = Path("catalog.json")
_summary_env = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
SUMMARY_FILE = Path(_summary_env) if _summary_env else None
TODAY = date.today().isoformat()

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def signer_sha256(apk: APK) -> str:
    """Sertifika DER baytlarinin SHA-256'sini (64 kucuk harf hex) dondurur.

    get_signature() v1 imza blogunun ham verisini dondurdugu icin kullanilmaz.
    Sertifika DER'i sirasiyla v3, v2, v1'den alinir. Birden fazla imzaci
    sertifikasi varsa hata verilir.
    """
    last_error: Optional[Exception] = None
    for method_name in (
        "get_certificates_der_v3",
        "get_certificates_der_v2",
        "get_certificates_der_v1",
    ):
        method = getattr(apk, method_name, None)
        if method is None:
            continue
        try:
            certs = method()
        except Exception as exc:
            last_error = exc
            continue
        if not certs:
            continue
        if len(certs) > 1:
            raise ValueError(
                f"{method_name}: birden fazla imzaci sertifikasi ({len(certs)}); tek imzaci bekleniyor"
            )
        cert = certs[0]
        if isinstance(cert, str):
            cert = cert.encode()
        if not cert:
            continue
        return hashlib.sha256(cert).hexdigest().lower()
    if last_error is not None:
        raise ValueError(f"Sertifika DER alinamadi: {last_error}")
    return ""


def tv_flags(apk: APK) -> Tuple[bool, bool]:
    """(tvSupported, tvOnly) doner.

    android.software.leanback ozelligi veya LEANBACK_LAUNCHER kategorisi
    varsa tvSupported=True. Leanback var, normal LAUNCHER yoksa tvOnly=True.
    """
    manifest = ""
    try:
        axml = apk.get_android_manifest_axml()
        if axml is not None:
            raw = axml.get_xml()
            manifest = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
    except Exception:
        manifest = str(getattr(apk, "xml", {}))

    features = []
    try:
        features = apk.get_features() or []
    except Exception:
        pass
    permissions = []
    try:
        permissions = apk.get_permissions() or []
    except Exception:
        pass

    has_leanback_feature = "android.software.leanback" in features or "android.software.leanback" in permissions
    has_leanback_launcher = "LEANBACK_LAUNCHER" in manifest
    has_launcher = "android.intent.category.LAUNCHER" in manifest

    tv_supported = bool(has_leanback_feature or has_leanback_launcher)
    tv_only = bool(tv_supported and (has_leanback_feature or has_leanback_launcher) and not has_launcher)
    return tv_supported, tv_only


def short_name(package: str) -> str:
    last = package.split(".")[-1].replace("_", "-").lower()
    return re.sub(r"[^a-z0-9-]", "-", last) or "app"


def safe_basename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def summarize(text: str) -> None:
    """Hata nedenini GITHUB_STEP_SUMMARY'ye ekler (stdout'a da basar)."""
    print(text)
    if SUMMARY_FILE and SUMMARY_FILE.exists():
        with SUMMARY_FILE.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")


class Processor:
    def __init__(self) -> None:
        self.catalog: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.commit_messages: List[str] = []
        self.moved: List[Tuple[Path, Path]] = []
        self.deleted: List[Path] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)
        summarize("## APK Katalog Hatası\n\n" + message)

    def load(self) -> bool:
        if not CATALOG_FILE.exists():
            self.fail(f"{CATALOG_FILE} bulunamadi")
            return False
        try:
            self.catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.fail(f"catalog.json gecersiz JSON: {exc}")
            return False
        return True

    def read_sidecar(self, apk_path: Path) -> Dict[str, Any]:
        """inbox/<ad>.json veya inbox/<ad>.apk.json yan dosyasini okur."""
        candidates = [
            INBOX_DIR / (apk_path.stem + ".json"),
            INBOX_DIR / (apk_path.name + ".json"),
        ]
        for sidecar in candidates:
            if sidecar.exists():
                try:
                    data = json.loads(sidecar.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{sidecar.name} gecersiz JSON: {exc}")
                sidecar.unlink()
                self.deleted.append(sidecar)
                return data
        return {}

    def process_one(self, apk_path: Path) -> None:
        print(f"Islem: {apk_path.name}")
        try:
            apk = APK(str(apk_path))
            package = apk.package
            version_name = apk.version_name
            version_code = int(apk.version_code)
            app_name = apk.get_app_name() or package
            min_sdk = int(apk.get_min_sdk_version() or 0)
            digest = sha256_file(apk_path)
            signer = signer_sha256(apk)
            tv_supported, tv_only = tv_flags(apk)

            print(f"  {package} {version_name} ({version_code}), minSdk={min_sdk}")
            print(f"  sha256={digest}")
            print(f"  signerSha256={signer}")
            print(f"  tvSupported={tv_supported} tvOnly={tv_only}")

            if not signer or not HEX64.match(signer):
                raise ValueError("imza sertifikasi SHA-256 hesaplanamadi (64 hex bekleniyor)")

            existing = next((a for a in self.catalog.get("apps", []) if a.get("id") == package), None)

            # Ayni surum reddi: mevcut en yuksek versionCode'a esit veya kucukse.
            if existing is not None:
                codes = [int(v["versionCode"]) for v in existing.get("versions", [])]
                highest = max(codes) if codes else -1
                if version_code <= highest:
                    raise ValueError(
                        f"{package}: versionCode {version_code} mevcut en yuksek {highest}'den buyuk degil; "
                        f"{version_name} surumu reddedildi"
                    )

            # Hedef APK adi: <paket-son-parcasi>-<versionName>.apk
            target_name = f"{short_name(package)}-{version_name}.apk"
            target_path = APK_DIR / target_name
            if target_path.exists():
                raise ValueError(f"apk/{target_name} zaten var; ayni adli dosya reddedildi")

            sidecar = self.read_sidecar(apk_path)

            # Ikon: cikarilamazsa mevcut ikon korunur.
            ICONS_DIR.mkdir(parents=True, exist_ok=True)
            icon_path = ICONS_DIR / f"{short_name(package)}.png"
            if not icon_path.exists():
                self.extract_icon(apk, icon_path)

            # git mv ile tasima (dosya inbox'tan kaldirilir).
            APK_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "mv", str(apk_path), str(target_path)], check=True)
            self.moved.append((apk_path, target_path))
            if apk_path.exists():
                apk_path.unlink()
                self.deleted.append(apk_path)

            size_bytes = target_path.stat().st_size
            notes = str(sidecar.get("notes", "") or "")
            if not notes:
                notes = "Ilk eklenen surum." if existing is None else ""

            new_version = {
                "versionName": version_name,
                "versionCode": version_code,
                "apkUrl": BASE_URL + "apk/" + target_name,
                "sizeBytes": size_bytes,
                "sha256": digest,
                "signerSha256": signer,
                "releasedAt": TODAY,
                "notes": notes,
            }

            if existing is None:
                entry = {
                    "id": package,
                    "name": sidecar.get("name") or app_name,
                    "category": sidecar.get("category") or "Diğer",
                    "shortDescription": sidecar.get("shortDescription") or "",
                    "description": sidecar.get("description") or "",
                    "iconUrl": BASE_URL + "icons/" + icon_path.name,
                    "screenshots": sidecar.get("screenshots") or [],
                    "tvSupported": bool(sidecar.get("tvSupported", tv_supported)),
                    "tvOnly": bool(sidecar.get("tvOnly", tv_only)),
                    "addedAt": TODAY,
                    "minSdk": min_sdk,
                    "abis": [],
                    "versions": [new_version],
                }
                self.catalog.setdefault("apps", []).append(entry)
            else:
                # Mevcut kaydin yalnizca TV bayraklarini ve surusunu guncelle.
                if "tvSupported" not in sidecar:
                    existing["tvSupported"] = tv_supported
                if "tvOnly" not in sidecar:
                    existing["tvOnly"] = tv_only
                existing.setdefault("versions", []).insert(0, new_version)

            self.commit_messages.append(f"{sidecar.get('name') or app_name} {version_name}")
            print(f"  BASARILI: {target_name}")

        except Exception as exc:
            self.fail(f"{apk_path.name}: {exc}")
            self.rollback_files()

    def extract_icon(self, apk: APK, output: Path) -> None:
        try:
            icon = apk.get_icon()
            if not icon:
                return
            if isinstance(icon, (bytes, bytearray)):
                output.write_bytes(icon)
                return
            if hasattr(icon, "save"):
                icon.save(str(output))
                return
            src = Path(str(icon))
            if src.exists():
                shutil.copyfile(src, output)
        except Exception as exc:
            print(f"  Uyari: ikon cikarilamadi, mevcut ikon korunuyor: {exc}")

    def rollback_files(self) -> None:
        """Hata halinde tasinmasi yapilan dosyalari geri alir."""
        for source, target in reversed(self.moved):
            try:
                if target.exists():
                    shutil.move(str(target), str(source))
            except Exception:
                pass
        self.moved.clear()

    def validate(self) -> None:
        """Katalog sema ve icerik dogrulamasi."""
        catalog = self.catalog
        if catalog.get("catalogVersion") != 1:
            self.fail("catalogVersion 1 olmali")
        if catalog.get("updatedAt") != TODAY:
            self.fail(f"updatedAt bugun ({TODAY}) olmali")

        apps = catalog.get("apps")
        if not isinstance(apps, list):
            self.fail("apps bir dizi olmali")
            return

        for app in apps:
            for field in ("id", "name", "category", "shortDescription", "description",
                          "iconUrl", "screenshots", "tvSupported", "tvOnly",
                          "addedAt", "minSdk", "abis", "versions"):
                if field not in app:
                    self.fail(f"{app.get('id', '?')}: zorunlu alan eksik: {field}")

            versions = app.get("versions", [])
            if not isinstance(versions, list) or not versions:
                self.fail(f"{app.get('id')}: en az bir surum olmali")
                continue

            codes = []
            for ver in versions:
                for field in ("versionName", "versionCode", "apkUrl", "sizeBytes",
                              "sha256", "signerSha256", "releasedAt", "notes"):
                    if field not in ver:
                        self.fail(f"{app['id']}: surum alan eksik: {field}")
                if not HEX64.match(str(ver.get("sha256", ""))):
                    self.fail(f"{app['id']}/{ver.get('versionName')}: sha256 64 hex olmali")
                if not HEX64.match(str(ver.get("signerSha256", ""))):
                    self.fail(f"{app['id']}/{ver.get('versionName')}: signerSha256 64 hex olmali")
                if not str(ver.get("apkUrl", "")).startswith(BASE_URL):
                    self.fail(f"{app['id']}/{ver.get('versionName')}: apkUrl hatali")
                size = ver.get("sizeBytes")
                if not isinstance(size, int) or size <= 0:
                    self.fail(f"{app['id']}/{ver.get('versionName')}: sizeBytes hatali")
                local_apk = APK_DIR / Path(str(ver.get("apkUrl", ""))).name
                if local_apk.exists():
                    actual = local_apk.stat().st_size
                    if actual != size:
                        self.fail(f"{local_apk.name}: gercek boyut {actual}, katalogda {size}")
                    if sha256_file(local_apk) != ver["sha256"]:
                        self.fail(f"{local_apk.name}: SHA-256 katalogla eslesmiyor")
                codes.append(int(ver["versionCode"]))

            if any(codes[i] <= codes[i + 1] for i in range(len(codes) - 1)):
                self.fail(f"{app['id']}: surumler versionCode azalan sirada degil: {codes}")

    def commit(self, message: str) -> None:
        token = os.environ.get("GITHUB_TOKEN", "")
        repo = os.environ.get("GITHUB_REPOSITORY", "SamulVanunu/apk-magaza-katalog")
        branch = os.environ.get("GITHUB_REF_NAME", "main")

        def run(args: List[str]) -> None:
            proc = subprocess.run(args, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"{' '.join(args[:2])} basarisiz: {proc.stderr.strip()}")

        run(["git", "add", "-A"])
        run(["git", "commit", "-m", message])
        if token:
            url = f"https://x-access-token:{token}@github.com/{repo}.git"
            proc = subprocess.run(
                ["git", "push", "--quiet", url, f"HEAD:{branch}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if proc.returncode != 0:
                raise RuntimeError("git push basarisiz (token yetkisi/kimlik kontrol edilmeli)")
        else:
            print("Uyari: GITHUB_TOKEN yok, push yapilmadi (yerel test)")

    def run(self) -> int:
        print("=== APK KATALOG ISLEYICI ===")
        print(f"Calisma dizini: {Path.cwd()}")
        INBOX_DIR.mkdir(parents=True, exist_ok=True)

        if not self.load():
            return 1

        apks = sorted(INBOX_DIR.glob("*.apk"))
        if not apks:
            print("inbox/ klasorunde APK yok; islem yapilmadi.")
            return 0

        print(f"{len(apks)} APK bulundu.")
        for apk_path in apks:
            self.process_one(apk_path)

        # Dogrulamadan once updatedAt'i bugune ayarla (yalnizca bellekte).
        self.catalog["updatedAt"] = TODAY

        print("\n=== DOGRULAMA ===")
        self.validate()

        if self.errors:
            summarize(
                "\n".join(f"- {e}" for e in self.errors)
                + "\n\nCatalog.json degistirilmedi; islem basarisiz."
            )
            return 1

        # Butun APK'lar basariliysa tek seferde kaydet.
        CATALOG_FILE.write_text(
            json.dumps(self.catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        message = "katalog: " + ", ".join(dict.fromkeys(self.commit_messages))
        print(f"\nTum APK'lar basarili. Commit mesaji: {message}")
        try:
            self.commit(message)
        except Exception as exc:
            self.fail(f"Commit/push basarisiz: {exc}")
            return 1

        print(f"Ozet: {len(apks)} APK islendi, {len(self.errors)} hata.")
        return 0


if __name__ == "__main__":
    sys.exit(Processor().run())
