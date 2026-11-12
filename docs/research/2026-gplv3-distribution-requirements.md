# GNU GPLv3 Distribution & Compliance Requirements

**Document Type:** Technical & Legal Research Note  
**Author:** CB POS Remediation Team  
**Date:** 2026-11-12  
**Scope:** GNU GPLv3 Licensing, PyQt6 Obligations, Corresponding Source Distribution, and Third-Party Notices (Issue #817 / Batch 8.3)  
**Status:** DRAFT — OWNER AND LEGAL COUNSEL REVIEW REQUIRED BEFORE PUBLIC RELEASE

---

> [!WARNING]
> This document records technical research and statutory/licensing analysis for the distribution of CB POS.
> It does not constitute formal legal advice. A formal review by qualified intellectual property legal counsel
> remains required before the first public binary or source distribution.

---

## 1. Primary Sources & Authorities

1. **GNU General Public License, Version 3 (29 June 2007)**  
   - Free Software Foundation, Inc. (FSF)  
   - Official Text: `https://www.gnu.org/licenses/gpl-3.0.html` / `https://www.gnu.org/licenses/gpl-3.0.txt`
   - Key Sections:
     - **Section 1**: Definition of *Corresponding Source*.
     - **Section 4**: Conveying Verbatim Copies.
     - **Section 5**: Conveying Modified Source Versions.
     - **Section 6**: Conveying Non-Source Forms (Object Code / Binaries) and access to Corresponding Source.
     - **Section 10**: Automatic Licensing of Downstream Recipients; prohibition of imposing further restrictions.

2. **GNU GPL Frequently Asked Questions (FSF)**  
   - Source: `https://www.gnu.org/licenses/gpl-faq.html`
   - Key references:
     - *How are the GPL and other open source licenses different from other licenses?*
     - *If a library is released under the GPL (not the LGPL), does that mean that any software which uses it has to be under the GPL?* (Yes: applications linking against GPL libraries form a combined work subject to GPLv3).
     - *What is "Corresponding Source"?* (Section 1).
     - *Can I put the binaries on my HTTP/FTP server and put the source on a different Internet site?* (Section 6(d) requires clear directions next to the object code saying where to find the Corresponding Source).

3. **Riverbank Computing Limited — PyQt6 Licensing Policy**  
   - Riverbank Computing Limited, developers of PyQt bindings for Qt.  
   - Source: `https://riverbankcomputing.com/software/pyqt/license`
   - Core Rule:
     - PyQt6 is dual-licensed under the **GNU General Public License v3 (GPLv3)** and commercial terms.
     - If you develop an application using the free/open version of PyQt6 without purchasing a commercial license from Riverbank, your application is a combined work and must be licensed under the GNU General Public License version 3 (GPLv3).

4. **The Qt Company — Qt Licensing Overview**  
   - The Qt Company  
   - Source: `https://www.qt.io/licensing/`
   - Core Rule:
     - Qt 6 libraries are available under commercial licenses and open-source licenses (LGPLv3 and GPLv3). PyQt6 links dynamically against Qt 6 runtime shared libraries.

---

## 2. Technical Licensing Decisions & Conflict Resolution

### 2.1 Owner Resolution (Decision D27 confirming D8)
In Decision D8 (2026-10-23) and reaffirmed by owner decision on 2026-11-12 (recorded as Decision D27 in `docs/remediation/DECISIONS.md`), CB POS adopts the **GNU General Public License version 3 (GPLv3)** path:
- PyQt6 is retained.
- CB POS is free and open-source software under GPLv3.
- Every distributed binary release provides complete corresponding source code for that exact version via public tagged repository link (`https://github.com/HMAHD/CB-POS/tree/v{version}`).
- Closed-source freeware EULAs and GPL-incompatible terms (e.g., "no resale", "no modification", or proprietary non-compete clauses) are rejected and superseded.

### 2.2 Definition & Conveyance of "Corresponding Source" (GPLv3 §1 & §6)
Under GPLv3 Section 1:
> *"The 'Corresponding Source' for a work in object code form means all the source code needed to generate, install, and (for an executable work) run the object code and to modify the work, including scripts to control those activities."*

Compliance Implementation:
1. **Public Repository**: Source code lives in the public repository `HMAHD/CB-POS`.
2. **Exact Version Tagging**: Release tags (e.g. `v1.3.0`) are permanently pushed to `HMAHD/CB-POS`. The durable link `https://github.com/HMAHD/CB-POS/tree/v{version}` provides access to the exact source matching the binary.
3. **Build Scripts & Configuration**: The repository contains `pyproject.toml`, `uv.lock`, `cbpos.spec`, `installer/cbpos.iss`, `create_installer.py`, and GitHub Action workflow `.github/workflows/release.yml`. This constitutes the complete build control scripts required by Section 1.
4. **Releases Repository Distinction**: The `ceybyte/cbpos-releases` repository is used solely for hosting Windows binary installer assets (`.exe`) and `latest.json` update metadata. It does NOT contain the full application source; therefore, all download notices, `latest.json` (`source_url`), and About surfaces must explicitly link to `HMAHD/CB-POS` at the corresponding tag.

### 2.3 Bundling & Notice Requirements
Under GPLv3 Sections 4, 5, and 6:
- The full, unmodified text of the GNU General Public License v3 must be included with every distributed copy of the software (`LICENSE`).
- The Inno Setup Windows installer must present the licence text via `LicenseFile=..\LICENSE`.
- PyInstaller must package `LICENSE`, `PRIVACY.md`, and `THIRD_PARTY_NOTICES.txt` inside the distribution bundle so that offline installations provide full legal notices.
- The UI (About surface) must expose immediate offline access to the licence, privacy notice, third-party notices, and repository source link.

---

## 3. Third-Party Notices & Dependency Closure

Under Section 4 and downstream open-source licenses (MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, LGPLv3, SIL OFL 1.1), copyright and permission notices of all bundled components must be preserved and conveyed.

1. **Deterministic Generator**: `scripts/gen_third_party_notices.py` extracts the complete transitive runtime dependency closure from `pyproject.toml` and `uv.lock`.
2. **Excluded Packages**: Development and build-only groups (`dev`, `build` such as `pytest`, `ruff`, `sphinx`, `pyinstaller`) are excluded from runtime distribution notices.
3. **Bundled Non-Package Assets**:
   - **Qt 6**: The Qt Company (LGPLv3 / GPLv3)
   - **PyQt6**: Riverbank Computing Limited (GPLv3)
   - **Font Awesome Free (via QtAwesome)**: Fonticons, Inc. (SIL OFL 1.1 for fonts, CC BY 4.0 for icons, MIT for code)
   - **Google Noto Sans Fonts (Latin, Sinhala, Tamil)**: Google LLC (SIL Open Font License 1.1)
   - **SVG Interface Icons**: Lucide / custom UI assets (MIT License)
4. **Fail-Closed Rule**: If an installed or transitive runtime dependency lacks identifiable licence information in both its package metadata and the verified override table, the generator must fail closed (raise an error and stop the build).

---

## 4. Required Next Steps for Owner & Counsel

1. **Legal Counsel Review**: Retain qualified Sri Lankan and international open-source legal counsel to review `LICENSE`, `PRIVACY.md`, and `THIRD_PARTY_NOTICES.txt` prior to the public 1.3.0 binary release.
2. **Trademark Clarification**: Ensure Ceylon Byte (Pvt) Ltd trademarks (CB POS logo and trade name) are clearly identified in accordance with Section 7(e) of GPLv3 (preserving trademark attribution without restricting downstream copyright freedoms).
3. **Translations Follow-up**: Authorize a professional legal translation service to translate `PRIVACY.md` into Sinhala and Tamil.

