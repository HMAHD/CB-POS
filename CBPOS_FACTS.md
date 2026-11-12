# CB POS — Product Fact Sheet & Verification Audit

*Audited for Phase 8.4 Pre-Release Integrity (Issue #818, RELEASE_PLAN.md §0.12 P12)*

---

## 1. Product Identity & Licensing

| Fact | Audited Value | Status / Evidence |
|---|---|---|
| **Product Name** | CB POS | Verified (`cbpos/config.py`) |
| **Current Version** | 1.3.0 (Pre-release) | Verified (`cbpos/core/services/update_service.py`) |
| **License** | GNU General Public License v3.0 (GPLv3) | Verified (`LICENSE`, Decision D27) |
| **Corresponding Source** | `https://github.com/HMAHD/CB-POS/tree/v{version}` | Verified (`README.md`, `AboutDialog`, `public-releases-readme.md`) |
| **Distribution Model** | Free and open source desktop software | Verified |
| **Target Audience** | Sri Lankan retail shops (grocery, pharmacy, hardware, clothing) | Verified (`PRODUCT.md`) |

---

## 2. Technology & Architecture

| Fact | Audited Value | Status / Evidence |
|---|---|---|
| **Runtime** | Python 3.12+ | Verified (`pyproject.toml`) |
| **GUI Framework** | PyQt6 6.11.0+ | Verified (`pyproject.toml`, `uv.lock`) |
| **Default Database** | SQLite with SQLAlchemy 2.0 ORM | Verified (`cbpos/core/database.py`) |
| **Multi-Terminal Options** | 1) LAN Sync (peer-to-peer over HTTP/TLS)<br/>2) PostgreSQL network database | Verified (`cbpos/infrastructure/sync_server.py`, `cbpos/core/database.py`) |
| **Packaging & Distribution** | PyInstaller one-dir (`dist/cbpos/cbpos.exe`) + Inno Setup installer (`cbpos.iss`) | Verified (`cbpos.spec`, `installer/cbpos.iss`) |
| **Data Storage Location** | `%LOCALAPPDATA%\CB POS` (Windows)<br/>`~/Library/Application Support/CB POS` (macOS)<br/>`~/.local/share/cbpos` (Linux) | Verified (`cbpos/config.py`) |

---

## 3. Internationalization (i18n)

| Fact | Audited Value | Status / Evidence |
|---|---|---|
| **Supported Languages** | English (`en`), Sinhala (`si`), Tamil (`ta`) | Verified (`cbpos/i18n/`) |
| **Total Translation Keys** | 3,212 keys | Verified (`scripts/validate_translations.py --strict`) |
| **Translation Coverage** | English: 100% (3,212/3,212)<br/>Sinhala: 97%+ (3,146/3,212)<br/>Tamil: 97%+ (3,142/3,212) | Verified (untranslated keys are technical terms/abbreviations) |
| **UI Language Switching** | Prompts for application restart to reinitialize UI widgets cleanly | Verified (`cbpos/ui/views/settings_view.py:523-532`) |
| **Receipt Language** | Independent of UI language; Sinhala/Tamil text printed via text rasterization | Verified (`cbpos/infrastructure/hardware/escpos_driver.py`) |

---

## 4. Sri Lankan Tax Compliance

| Fact | Audited Value | Status / Evidence |
|---|---|---|
| **Pricing Model** | Maximum Retail Price (MRP) tax-inclusive backward calculation | Verified (`cbpos/core/services/tax_service.py`) |
| **Default State** | VAT and SSCL are disabled by default until "VAT registered" is enabled | Verified (`TaxService.is_vat_active()`, `ConfigService`) |
| **VAT Rate** | 18.0% | Verified (`cbpos/core/services/tax_service.py`) |
| **SSCL Rate** | 2.5% | Verified (`cbpos/core/services/tax_service.py`) |
| **SSCL Taxable Base** | VAT-exclusive turnover per SSCL Act s.3(3)(b): `mrp / 1.18` | Verified (`TaxService.calculate_taxes`) |
| **SSCL Turnover Presets** | Retail: 50%, Manufacturer: 85%, Distributor: 25%, Custom | Verified (`SSCL_PRESETS`, Decision D25) |
| **Gross Rs 100 Breakdown** | On Rs 100.00 gross (Retail preset):<br/>- Output VAT: Rs 15.25<br/>- SSCL: Rs 1.06<br/>- Net Revenue: Rs 83.69 | Verified (`TaxService.calculate_taxes(Decimal("100.00"))`) |
| **Tax Invoices** | Mandated 2026 format: serial `YYMMM_QQQQ_XXXXX`, buyer/supplier particulars, amount in words, `ORIGINAL` / `COPY ONLY` markings | Verified (`cbpos/core/services/tax_invoice_service.py`) |
| **Customer Receipts** | Standard receipts omit SSCL (tracked in back-office tax reports only) | Verified (Decision D9, D25) |

---

## 5. Hardware & Peripherals

| Fact | Audited Value | Status / Evidence |
|---|---|---|
| **Receipt Printers** | ESC/POS 58mm and 80mm thermal printers via USB (`pyusb` / `python-escpos`) | Verified (`cbpos/infrastructure/hardware/escpos_driver.py`) |
| **Barcode Scanners** | Standard USB HID keyboard-emulation scanners (sub-50ms scan latency) | Verified (`cbpos/infrastructure/input_manager.py`) |
| **Weighing Scales** | Serial / Virtual COM port interfaces | Verified (`cbpos/infrastructure/hardware/scale_driver.py`) |
| **Barcode Generation** | Real barcode symbologies (`python-barcode`: EAN-13 for 13 digits, CODE128 otherwise) | Verified (`cbpos/core/services/label_service.py`) |
| **Label Sizing** | 50×30 mm, 40×25 mm, 58 mm receipt width, and custom dimensions | Verified (`cbpos/core/services/label_service.py`) |

---

## 6. Privacy & Security

| Fact | Audited Value | Status / Evidence |
|---|---|---|
| **Telemetry / Tracking** | Zero telemetry, zero analytics, zero external logging | Verified (`PRIVACY.md`) |
| **Network Calls** | Optional GitHub Releases version query on startup (can be disabled in Settings > System) | Verified (`cbpos/core/services/update_service.py`) |
| **Access Control (RBAC)** | Role-based permissions (Admin, Manager, Cashier) with manager override | Verified (`cbpos/core/services/auth_service.py`) |
| **Authentication** | bcrypt PIN hashing | Verified (`cbpos/core/services/auth_service.py`) |
| **Audit Trails** | All critical operations (voids, refunds, price changes, reprints) logged to `AuditLog` | Verified (`cbpos/core/models/`) |

---

## 7. Verification Caveats & Pending Checks

| Area | Status / Caveat | Action |
|---|---|---|
| **Physical Printing** | Tested in test harness and virtual spoolers; exact physical thermal print alignment varies across manufacturer chipsets | Marked `⚠️ Verify on Windows` pending physical shop hardware testing |
| **Windows Release Installer** | Built and signed via GitHub Actions release workflow on Windows runners | Verified via CI |

