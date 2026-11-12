# CB POS Privacy Notice

**Status:** DRAFT — OWNER AND LEGAL REVIEW REQUIRED BEFORE PUBLIC RELEASE  
**Effective Date:** 2026-11-12  
**Applies To:** CB POS Desktop Application (Windows, Linux, macOS)

---

> [!IMPORTANT]
> **Notice to Shop Owners:** CB POS is an offline-first Point of Sale application designed and built by
> Ceylon Byte (Pvt) Ltd ("CeyByte"). **The app does not automatically send shop data to CeyByte.**
> Your data belongs to you and remains on your computer or your shop's private local network.
> No data is sent automatically to CeyByte.
>
> This notice describes every network path, data storage location, and third-party interaction present
> in the CB POS application.

---

## 1. Zero Telemetry & Analytics Guarantee

We have conducted a full audit of the CB POS codebase. CB POS contains:
- **No telemetry** or usage tracking;
- **No background analytics** (no Google Analytics, Mixpanel, PostHog, or similar tracking libraries);
- **No remote error monitoring** (no Sentry, Crashlytics, or remote crash reporting beacons);
- **No advertising identifiers** or tracking cookies.

CB POS does not monitor how often you open the software, how many transactions you ring up, what products you sell, or what revenue you make.

---

## 2. Inventory of Network Activity in Shipped Code

CB POS only connects to a network under the following five specific, user-controlled conditions:

### 2.1 Software Update Checks & Downloads
- **Purpose:** Checks whether a newer version of CB POS is available, downloads changelog notes, and downloads updated installer packages if you choose to install them.
- **What is Sent:** A standard HTTP GET request to GitHub (`https://raw.githubusercontent.com/ceybyte/cbpos-releases/main/latest.json` and `https://github.com/ceybyte/cbpos-releases/releases/`). No shop data, hardware serials, IP addresses, database identifiers, or customer records are sent.
- **Control:** You can turn off automatic update checks at any time in **Settings → System** by unchecking *"Check for CB POS updates when it starts"*. You can also trigger a manual check at any time using the **Check now** button.

### 2.2 Email Receipts & Scheduled Daily Reports (SMTP)
- **Purpose:** Delivers e-receipts to customers or automated daily summary reports to the shop owner or accountant.
- **Where it Connects:** Connects directly and exclusively to your shop's user-configured outgoing email server (SMTP host, port, username, password, and encryption settings configured in **Settings → Email**).
- **What is Sent:** Only the email body and receipt or PDF report explicitly requested by the operator or scheduled by the owner.
- **Data Destination:** Data goes directly to your configured email provider (e.g., your Google Workspace, Microsoft 365, or private mail server). It is never routed through or copied to CeyByte servers.

### 2.3 Shop Local Network Synchronization (LAN Sync)
- **Purpose:** Allows multiple checkout terminals (tills) within the same physical shop to synchronize transactions and stock levels with the Main PC.
- **Where it Connects:** Operates strictly within your shop's Local Area Network (LAN) over private IP addresses (e.g., `192.168.x.x` or `10.x.x.x`) on a configured local port (default: 8000).
- **Security:** Communications between the Main PC and secondary terminals are authenticated via a private shared sync pairing token.
- **Internet Exposure:** LAN sync does not transmit data over the public internet and does not connect to external servers.

### 2.4 Shop-Configured PostgreSQL Database (Optional)
- **Purpose:** In multi-terminal or enterprise retail setups, CB POS can connect to an external PostgreSQL database instead of the default local SQLite database.
- **Where it Connects:** Connects only to the database server IP or hostname entered by the shop administrator in **Settings → Database** or during initial setup.
- **Data Destination:** All database records reside on your designated database server. CeyByte has no access or connection to your database.

### 2.5 User-Initiated External Browser Links
When you choose to click a help or web link inside CB POS (such as the User Guide, Report a Problem, Suggest a Feature, or CeyByte Website):
- **External Hand-off:** CB POS launches your computer's default web browser (such as Microsoft Edge, Google Chrome, or Mozilla Firefox) and opens the standard HTTPS web address.
- **Normal Web Request:** Opening a link in your web browser creates a normal website request from your browser to `ceybyte.com` or `github.com`.
- **Zero Prefill of Shop Data:** CB POS never prefills, encodes, or transmits customer details, product inventories, sales values, shop names, database contents, log files, or file paths in link URLs or parameters.
- **Feedback & Bug Reporting:**
  - Submitting feedback on `ceybyte.com` requires signing in with a Google account in your browser to prevent automated spam.
  - **Your Google credentials, access tokens, and passwords stay strictly inside your web browser and are NEVER seen, handled, or received by CB POS.**
  - The CeyByte feedback website and Google operate under their own separate terms of service and privacy policies.

---

## 3. Local Data Storage & Security

CB POS stores all business records locally on the computer where it is installed:

- **Windows Location:** `%LOCALAPPDATA%\CB POS` (typically `C:\Users\<Username>\AppData\Local\CB POS`)
- **macOS Location:** `~/Library/Application Support/CB POS`
- **Linux Location:** `~/.local/share/cbpos`

### Files Stored Locally:
1. **`cbpos.db`**: SQLite database containing all products, categories, sales, refund records, customer balances, loyalty points, supplier payables, tax invoices, and audit logs.
2. **`settings.json`**: Application preferences, printer configurations, and hardware settings.
3. **`.key`**: Local cryptographic key used for sensitive credential encryption (e.g. SMTP password storage).
4. **`logs/`**: Local diagnostic log files recording application events and errors. Logs are kept on your hard drive for troubleshooting and are never uploaded automatically.
5. **`backups/`**: Compressed and encrypted database backups created manually or automatically.

Updating CB POS or running the Windows installer does not overwrite or remove your data folder.

---

## 4. User Rights & Data Control

Because CB POS is an offline-first system:
- **Full Ownership:** You own 100% of the data recorded in the application.
- **Exporting Data:** You can export sales history, customer ledgers, supplier statements, inventory lists, and tax filing summaries to CSV or Excel at any time via the Management interface.
- **Data Deletion:** You can delete or reset data by clearing the database or removing the `%LOCALAPPDATA%\CB POS` directory when the application is closed.

---

## 5. Contact & Inquiries

If you have questions about privacy or data security in CB POS, contact CeyByte:
- **Website:** `https://ceybyte.com/legal/privacy/`
- **Email:** `privacy@ceybyte.com`
- **Entity:** Ceylon Byte (Pvt) Ltd, Sri Lanka

---

*Note: Formal professionally translated Sinhala and Tamil versions of this Privacy Notice are tracked for legal translation review before the final public release.*
