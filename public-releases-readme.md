<p align="center">
  <img src="assets/CBPOS_Banner.png" alt="CB POS Banner" width="600">
</p>

<h1 align="center">CB POS</h1>
<h3 align="center">Free Point of Sale for Sri Lankan Retail</h3>

<p align="center">
  <a href="https://github.com/ceybyte/cbpos-releases/releases/latest"><img src="https://img.shields.io/github/v/release/ceybyte/cbpos-releases?style=for-the-badge&color=00BCEB&label=Download" alt="Latest Release"></a>
  <img src="https://img.shields.io/badge/Platform-Windows%2010+-0078D6?style=for-the-badge&logo=windows" alt="Windows 10+">
  <img src="https://img.shields.io/badge/Price-Free-39FF14?style=for-the-badge" alt="Free">
  <img src="https://img.shields.io/badge/Languages-EN%20%7C%20%E0%B7%83%E0%B7%92%E0%B6%82%E0%B7%84%E0%B6%BD%20%7C%20%E0%AE%A4%E0%AE%AE%E0%AE%BF%E0%AE%B4%E0%AF%8D-FFDC00?style=for-the-badge" alt="Trilingual">
</p>

<p align="center">
  <a href="#-download--install">Download</a> &bull;
  <a href="#-features">Features</a> &bull;
  <a href="#-getting-started">Getting Started</a> &bull;
  <a href="#-faq">FAQ</a> &bull;
  <a href="#-support">Support</a>
</p>

---

## Why CB POS?

Built specifically for Sri Lankan shop owners — grocery stores, pharmacies, hardware shops, clothing boutiques, and everything in between. No monthly fees, no internet required, no IT team needed.

- **Works offline** — your sales never stop, even when the WiFi does
- **Trilingual** — switch between English, Sinhala, and Tamil instantly
- **Tax compliant** — VAT (18%) and SSCL (2.5%) calculated automatically from MRP
- **Just install and start selling** — setup takes less than 5 minutes

---

## Features

### Fast Checkout
- Barcode scanning with sub-50ms response
- Keyboard shortcuts for every action — your cashier never needs to touch the mouse
- Touch-screen product grid for quick picks
- Hold and recall bills, split payments, multi-payment support

### Inventory Management
- Track stock for thousands of products
- Weighted items (kg, g, L) with 3 decimal places
- Composite/bundle items (e.g., gift pack = 3 separate products)
- Stock take and adjustment with audit trail
- Low stock alerts on the dashboard

### Customer Credit Book
- Maintain customer credit accounts with limits
- Record payments against outstanding balances
- Print customer statements

### Receipts & Printing
- Thermal receipt printing (ESC/POS) in Sinhala, Tamil, or English
- Receipt reprinting from sale history
- Product label printing
- A4 tax invoice generation (PDF)

### Reports & Dashboard
- Daily sales summary, inventory valuation, cash flow
- Export to Excel, CSV, or PDF
- Real-time dashboard with top products and KPIs

### Security
- Role-based access: Admin, Manager, Cashier
- Manager override PIN for restricted operations (void, refund, price change)
- Full audit trail for every critical action
- Shift management with opening/closing float

### Tax Compliance
- Sri Lankan VAT (18%) backward calculation from MRP
- SSCL (2.5% on 50% of revenue)
- Per-category tax exemption (e.g., pharmacy, rice)
- Tax filing summary report for monthly/quarterly returns

---

## Download & Install

### System Requirements

| Requirement | Minimum |
|------------|---------|
| Operating System | Windows 10 or later |
| RAM | 4 GB |
| Disk Space | 200 MB |
| Screen Resolution | 1280 x 720 |
| Printer (optional) | Any ESC/POS thermal printer |
| Scanner (optional) | Any USB barcode scanner |

### Installation Steps

1. **Download** the latest installer from the [Releases page](https://github.com/ceybyte/cbpos-releases/releases/latest)
2. **Run** `CBPOSSetup-x.x.x.exe`
3. If Windows SmartScreen appears, click **"More info"** then **"Run anyway"** — the app is safe, we just haven't purchased a code signing certificate yet
4. Follow the installer — it takes about 30 seconds
5. Launch CB POS from the desktop shortcut

### First Launch

On the first launch you'll see:
1. **Setup Wizard** — enter your shop name, select your printer, and set an admin PIN
2. **Database Choice** — pick **"Start Fresh"** for a clean database, or **"Load Demo Data"** to explore with sample products and sales already loaded

**Default login:** Username `admin`, PIN `1234` (change this immediately in Settings)

---

## Getting Started

1. **Log in** with `admin` / `1234`
2. **Add your products** — go to Management > Inventory > Add Product
3. **Set up categories** — organize products into groups for easy browsing
4. **Add customers** (optional) — for credit sales and loyalty tracking
5. **Configure your printer** — Settings > Hardware > Receipt Printer
6. **Start selling!** — scan barcodes or search by name, press F12 or click Pay

### Keyboard Shortcuts (POS Screen)

| Key | Action |
|-----|--------|
| `F1` | Help / Shortcuts |
| `F2` | Select Customer |
| `F4` | Change Quantity |
| `F6` | Hold Bill |
| `F7` | Recall Bill |
| `F8` | Open Cash Drawer |
| `F12` | Pay / Checkout |
| `Del` | Void Bill |

---

## What's Included

| Component | Description |
|-----------|-------------|
| POS Checkout | Main sales screen with cart, payments, receipts |
| Inventory | Products, categories, stock adjustments, stock take |
| Purchase Orders | Supplier management, GRN, cost tracking |
| Customer CRM | Credit book, statements, payment recording |
| Reporting | 9 built-in reports with Excel/PDF export |
| Tax Module | VAT/SSCL compliance, tax invoices |
| User Management | Roles, permissions, audit logs |
| Backup & Restore | One-click database backup |

---

## FAQ

**Is this really free?**
Yes. CB POS is completely free to use for any type of shop. There are no hidden fees, no trial periods, and no feature limits.

**Does it work without internet?**
Yes. Everything runs locally on your computer using a local database. No internet connection is required for any feature.

**What printers are supported?**
Any ESC/POS compatible thermal receipt printer (most 58mm and 80mm printers). For A4 documents, any Windows printer works.

**Can I print receipts in Sinhala?**
Yes. Receipts can be printed in Sinhala, Tamil, or English — independently of your UI language.

**Is my data safe?**
Your data is stored locally on your computer. Use the built-in backup feature (Settings > Backup) to create regular backups to a USB drive or external folder.

**Can multiple cashiers use it?**
Yes. Create separate user accounts with different roles (Admin, Manager, Cashier). Each user logs in with their own PIN.

**Can I use it on multiple computers?**
The current version is designed for single-computer use. Multi-terminal support (network mode) is planned for a future release.

**How do I report a bug?**
Open an issue on this repository's [Issues page](https://github.com/ceybyte/cbpos-releases/issues), or contact us at the email below.

**Is this open source?**
No. CB POS is free software but the source code is not publicly available.

---

## Version History

See the [Releases page](https://github.com/ceybyte/cbpos-releases/releases) for all versions and changelogs.

### Latest: v1.2.2 (March 2026)
- Sale History dialog with browse, reprint, and inline refund
- First-run database setup (empty or demo)
- Trilingual support (English, Sinhala, Tamil)
- Tax compliance (VAT/SSCL)
- 80+ bug fixes and improvements

---

## Security

If you discover a security vulnerability, please report it responsibly:

- **Email:** security@ceybyte.com
- **Do NOT** create a public issue for security bugs
- We will acknowledge receipt within 48 hours

---

## Support

| Channel | Contact |
|---------|---------|
| Bug Reports | [GitHub Issues](https://github.com/ceybyte/cbpos-releases/issues) |
| Email | support@ceybyte.com |
| Website | [ceybyte.com](https://ceybyte.com) |

---

<p align="center">
  <img src="assets/CBPOS_Logo.png" alt="CB POS Logo" width="80">
  <br>
  <strong>CB POS</strong> by <a href="https://ceybyte.com">Ceylon Byte</a>
  <br>
  <sub>Free Point of Sale for Sri Lankan Retail</sub>
  <br><br>
  <sub>&copy; 2026 Ceylon Byte. All rights reserved.</sub>
</p>
