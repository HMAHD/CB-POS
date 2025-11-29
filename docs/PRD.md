# 🚀 PRODUCT REQUIREMENTS DOCUMENT (PRD)
## **Product Name:** CB POS (Ceylon Byte Point of Sale)
**Version:** 1.0 (Master Blueprint)
**Status:** Approved for Development
**Target Market:** Sri Lankan Retail (Grocery, Hardware, Textile, Electronics)
**Tech Stack:** Python 3.12+ | PyQt6 | SQLite/PostgreSQL | SQLAlchemy

---

## 1. EXECUTIVE SUMMARY
**CB POS** is a high-performance, offline-first retail management system designed specifically for the Sri Lankan market. Unlike fragile web-based systems, it is built as a native desktop application to ensure **zero-latency operation** and **100% reliability** during power or internet outages.

It combines the feature richness of enterprise ERPs (like Aronium) with the speed of an industrial tool. It is "Keyboard-First," allowing cashiers to operate without a mouse, and "Compliance-Ready," handling Sri Lankan VAT/SSCL calculations in the background while keeping the user experience simple.

---

## 2. TECHNICAL ARCHITECTURE

### 2.1 Core Stack
| Component | Technology | Rationale |
| :--- | :--- | :--- |
| **Language** | Python 3.12+ | Rapid development, vast library support for hardware. |
| **GUI Framework** | PyQt6 (Qt 6) | Industry standard for stable, high-DPI, cross-platform UIs. |
| **Database (Local)** | SQLite | Zero-configuration, corruption-resistant, single-file DB. |
| **Database (Server)**| PostgreSQL | Optional for multi-terminal setups (Client-Server mode). |
| **ORM** | SQLAlchemy 2.0 | Type-safe database interactions and migration support. |
| **Hardware** | `python-escpos`, `pyusb` | Direct low-level control of Thermal Printers & Scanners. |
| **Styling** | QSS (Qt Style Sheets) | CSS-like styling for a modern, branded look. |

### 2.2 System Design Principles
1.  **Offline-First:** The system *always* writes to the local DB first. Cloud sync (if enabled) happens asynchronously in the background.
2.  **Modular MVC:** strict separation of **Model** (Database), **View** (PyQt Widgets), and **Controller** (Business Logic).
3.  **Industrial Resilience:** Global Exception Handlers prevent crashes. If a printer fails, the app logs the error and continues the sale.
4.  **Zero Latency:** Barcode scan to Cart addition must occur in **< 50ms**.

---

## 3. SRI LANKAN COMPLIANCE & TAX MODULE 🇱🇰

### 3.1 "Backward Calculation" Engine
Since Sri Lankan retail prices are **MRP (Maximum Retail Price)** (Tax Inclusive), the system calculates tax liabilities backward for reporting.

* **Logic:** `Shelf Price = Base Price + VAT + SSCL`
* **VAT Engine:**
    * **Rate:** Configurable (Default: **18%**).
    * **Formula:** `Taxable Value = Total Sales / 1.18`.
* **SSCL (Social Security Contribution Levy) Engine:**
    * **Rate:** Configurable (Default: **2.5%**).
    * **Liable Turnover:** Configurable % of turnover (Default: **50%** for retail).
    * **Formula:** `SSCL Payable = (Turnover * 50%) * 2.5%`.

### 3.2 Owner’s Liability Dashboard
A secure, owner-only view to track tax obligations in real-time.
* [ ] **Daily Tax Meter:** Shows "Estimated Tax Payable" for the day/month.
* [ ] **Net Payable Calc:** `Output VAT (Sales) - Input VAT (Purchases) = Net Payable`.

### 3.3 Smart Invoicing
* [ ] **B2C Receipt:** Standard receipt. Footer: *"Prices include all applicable government taxes."*
* [ ] **B2B Tax Invoice:** Triggered if a customer with a VAT Reg Number is selected.
    * *Action:* Splits the receipt to show Base Value, VAT Amount, and Total separately.

---

## 4. USER INTERFACE & "CEYLON BYTE" THEME

### 4.1 Visual Identity
* **Theme Engine:** Real-time toggle between **Ceylon Day** and **Ceylon Night** modes.
* **Palette:**
    * **Navy Blue (`#001F3F`)**: Primary Backgrounds (Night).
    * **Cyan (`#00BCEB`)**: Primary Action Buttons / Active States.
    * **Neon Green (`#39FF14`)**: Payment Confirmation / Success.
    * **Signal Red (`#FF4136`)**: Void / Error / Low Stock.

### 4.2 Workspace Layouts
* **Touch Mode:** Grid-based "Visual Groups" for non-barcoded items (Vegetables, Bakery).
* **Keyboard Mode:** Dense list view. **Focus Trap** ensures the cursor is *always* in the scan box.

---

## 5. DETAILED FEATURE REQUIREMENTS

### Phase 1: Inventory & Product Management
* [ ] **Product Variants:** Parent Item (Shirt) -> Variants (Red/S, Red/M).
* [ ] **Composite Items:** "Hamper" sells 1 SKU but deducts 5 different inventory items.
* [ ] **Weighted Items:** Boolean flag `is_weighted`. Supports decimal quantities (e.g., `0.500` kg).
* [ ] **Low Stock Alerts:** Visual highlight when `Qty <= ReorderLevel`.
* [ ] **Barcode Intelligence:** Supports parsing weight-embedded barcodes (e.g., from deli scales `200050012500` -> Item 500, Weight 1.25kg).

### Phase 2: Sales Terminal (POS)
* [ ] **Smart Cart:**
    * **Merge Duplicates:** Scanning "Soap" twice updates Qty to 2, doesn't add a new row.
    * **Price Override:** Manager PIN required to change price at checkout.
    * **Line Discount:** % or Fixed discount per item.
* [ ] **Hold & Recall:** "Park" a bill (save state to DB) and recall it later.
* [ ] **Refund Wizard:** Scan original receipt barcode to auto-load items for return.
* [ ] **Keyboard Shortcuts:**
    * `F1`: Help Overlay
    * `F2`: Global Search (Fuzzy Logic)
    * `F5`: Pay / Tender
    * `F6`: Hold Bill
    * `F12`: Logout

### Phase 3: Payments & Checkout
* [ ] **Split Payments:** Pay Rs. 1000 Cash + Rs. 2000 Card on one bill.
* [ ] **Credit Sales:** "Charge to Account" for registered customers.
* [ ] **Smart Tender:** Auto-calculate change. Shortcuts for "Exact Amount", "5000", "1000".
* [ ] **Receipt Engine:**
    * Templates for 58mm and 80mm thermal paper.
    * Support for printing Sinhala/Tamil logos/headers (Image Mode).

### Phase 4: Customer Management (CRM)
* [ ] **Credit Limits:** Stop credit sales if user exceeds defined debt limit.
* [ ] **Loyalty Points:** Earn `X` points per `Y` Rupees. Redeem for discount.
* [ ] **Customer Groups:** "Wholesale" group gets automatic 5% discount level.

### Phase 5: Hardware Integration (HAL)
* [ ] **Printer Routing:** Drink orders print at Bar Printer, Food at Kitchen Printer.
* [ ] **Cash Drawer:** RJ11 kick signal sent only on Cash transactions.
* [ ] **Pole Display:** Send `Total: Rs. XXX` to customer-facing VFD display.

---

## 6. NON-FUNCTIONAL REQUIREMENTS

1.  **Performance:**
    * Application Startup: < 3 seconds.
    * Barcode Search: < 50ms (Indexed Local DB).
    * Transaction Commit: < 500ms.
2.  **Security:**
    * **PIN Hashing:** SHA-256.
    * **Role-Based Access (RBAC):** Granular permissions (e.g., `can_void_transaction`, `can_view_reports`).
3.  **Data Integrity:**
    * **ACID Transactions:** Inventory is deducted ONLY if the Sale is successfully saved.
    * **Auto-Backup:** Automatic `.zip` backup of `cbpos.db` to a specified folder on Exit.

---

## 7. DEPLOYMENT & UPDATE STRATEGY

* **Packaging:** Use **PyInstaller** to compile to a single `.exe` file.
* **Auto-Updater:**
    1.  `Launcher.exe` checks GitHub/S3 for `version.json`.
    2.  If update exists, download `.zip`.
    3.  Backup current DB.
    4.  Extract and overwrite binaries.
    5.  Launch new version.

---

## 8. GLOSSARY (Sri Lanka Context)
* **MRP:** Maximum Retail Price (Includes Tax).
* **GRN:** Goods Received Note (Stock Entry).
* **SSCL:** Social Security Contribution Levy.
* **COT:** Cash on Till (Expected Cash).

