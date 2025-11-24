# Product Requirements Document (PRD): CB POS

| Metadata | Details |
| :--- | :--- |
| **Product Name** | CB POS |
| **Developer** | Ceybyte.com |
| **Version** | 0.5 (Alpha) |
| **Target Platform** | Windows 10/11 (WinUI 3 Desktop) |
| **Tech Stack** | .NET 9, Entity Framework Core, SQLite |
| **Design Philosophy** | Industrial Grade, Offline-First, Keyboard-Centric |
| **Status** | 🟡 **Phase 2 (UI Implementation) - Currently Resolving Build Issues** |

---

## 1. Executive Summary
CB POS is a high-performance, industrial-grade Point of Sale system tailored for the Sri Lankan retail market. Unlike web-based POS systems, CB POS runs natively to ensure zero latency, handles power/internet interruptions gracefully (Offline-First), and supports Sinhala/Tamil natively. It prioritizes speed: keyboard-only operation for cashiers, with touch support as a secondary input.

---

## 2. Technical Architecture & Foundation

### 2.1 Core Stack `[STATUS: COMPLETED]`
* **Framework:** .NET 9 (Latest LTS/Stable).
* **UI Framework:** WinUI 3 (Windows App SDK 1.6+).
* **Deployment:** Unpackaged Executable (`.exe`), Self-Contained.
* **Database:** SQLite (Local file `cbpos.db` in AppData).
* **Architecture:** Modular Monolith / Clean Architecture.
    * `CB.POS.Core`: Entities, Interfaces (Pure C#).
    * `CB.POS.Infrastructure`: EF Core, Hardware Impl, File I/O.
    * `CB.POS.UI`: Views, ViewModels, DI Container.

### 2.2 Infrastructure Services `[STATUS: COMPLETED]`
* **Dependency Injection:** Microsoft.Extensions.Hosting (Generic Host).
* **Logging:** Serilog (File sink: `AppData/CB_POS/logs`).
* **Focus Management:** `KeyboardFocusService` (Auto-traps cursor for scanning).
* **Seeding:** `DbInitializer` auto-generates Admin user & SL Product Data.

---

## 3. Functional Requirements & Status

### Phase 1: Core Data & Authentication `[STATUS: COMPLETED]`
| ID | Feature | Description | Status |
| :--- | :--- | :--- | :--- |
| **1.1** | **User Entity** | `Employee` model with Name, Role, and `PinHash`. | ✅ Done |
| **1.2** | **Inventory Model** | `Product` (Barcode Indexed), `Category`, `IsWeighted` support. | ✅ Done |
| **1.3** | **Seed Data** | Auto-population of Sri Lankan products (Munchee, Highland, Keeris Samba). | ✅ Done |
| **1.4** | **Auth Logic** | PIN-based authentication service. | ✅ Done |

### Phase 2: User Interface (The Shell) `[STATUS: PARTIAL / BLOCKED]`
| ID | Feature | Description | Status |
| :--- | :--- | :--- | :--- |
| **2.1** | **Login Screen** | Touch-friendly Numpad, Masked Input, Error Handling. | 🟡 Implemented (Debugging) |
| **2.2** | **Main Shell** | `NavigationView` (Left Compact), Digital Clock, User Badge. | 🟡 Implemented (Debugging) |
| **2.3** | **Navigation** | `NavigationService` to switch frames (Login -> Shell). | 🟡 Implemented (Debugging) |
| **2.4** | **Visual Polish** | Mica Alt Backdrop, Theme Shadows, Animated Icons. | 🔴 **BLOCKED** (Build Error) |

### Phase 3: Sales Operations (The Engine) `[STATUS: IN PROGRESS]`
| ID | Feature | Description | Status |
| :--- | :--- | :--- | :--- |
| **3.1** | **Cart Logic** | `CartService`: Add/Remove, Calculate Totals, Decimal Qty (Weighted). | ✅ Done (Logic Only) |
| **3.2** | **Sales View** | Split-screen UI (Cart List vs. Totals), High Contrast. | 🚧 Pending Implementation |
| **3.3** | **Scanner Hook** | Global hook to capture Barcode Scanner input (vs Keyboard typing). | 🚧 Pending Implementation |
| **3.4** | **Payment** | Cash Tender, Change Calculation, Transaction Commit. | ⚪ Not Started |

### Phase 4: Hardware Integration `[STATUS: PLANNED]`
| ID | Feature | Description | Status |
| :--- | :--- | :--- | :--- |
| **4.1** | **Printing** | ESC/POS implementation via `ESCPOS_NET` (USB/LAN). | ⚪ Not Started |
| **4.2** | **Cash Drawer** | RJ11 trigger via Printer signal. | ⚪ Not Started |
| **4.3** | **Customer Display** | Secondary Window/Pole Display support. | ⚪ Not Started |

---

## 4. UI/UX Guidelines (Industrial Standard)

* **Keyboard First:** All critical actions must have F-Key shortcuts.
    * `F1`: Help
    * `F2`: Search
    * `F4`: Void Line
    * `F5`: Pay
    * `F12`: Logout
* **Focus Trap:** The cursor must aggressively return to the Barcode Input field after 200ms of inactivity.
* **Typography:**
    * **Sinhala/Tamil:** "Iskoola Pota" or "Nirmala UI".
    * **Numbers:** Monospaced font for alignment in lists.
* **Visuals:**
    * **Mica Alt:** Used for window background.
    * **ThemeShadows:** Used to separate the "Bill" from the "Background".

---

## 5. Localization Strategy `[STATUS: SETUP COMPLETE]`
* **Mechanism:** WinUI 3 PRI Resources (`.resw`).
* **Languages:**
    * `en-US` (Default)
    * `si-LK` (Sinhala)
    * `ta-LK` (Tamil)
* **Implementation:** All XAML strings use `x:Uid`.

---

## 6. AI Integration Roadmap `[STATUS: FUTURE]`
* **Smart Search:** Vector search for products (e.g., "Soap" -> finds "Body Wash").
* **Inventory Prediction:** "Based on last Poya day sales, you need 50 extra packets of Incense Sticks."
* **Natural Language Reporting:** "Show me total sales for Keeris Samba last week."

---

## 7. Current Critical Issues (The "Blockers")

**Priority 1: Build Pipeline Corruption**
* **Symptom:** `XamlCompiler.exe exited with code 1`.
* **Cause:** Likely namespace mismatch or corrupted `obj` artifacts following manual file reverts.
* **Solution Strategy:** "Project Transplant" (Recreating `CB.POS.UI` project clean) is the recommended next step to resume development.

**Priority 2: Zombie Processes**
* **Symptom:** `CB.POS.UI.exe` remains locked after closing.
* **Status:** **Resolved** (Added `ForceKill` target to `.csproj`).

---

## 8. Next Steps (Immediate Action Plan)

1.  **Resolve Build Error:** Execute the "Project Transplant" to get a clean, compiling UI project.
2.  **Restore Views:** Carefully migrate `LoginView`, `ShellView`, and `SalesView` code one by one, verifying namespaces.
3.  **UI Connection:** Connect `SalesViewModel` to the `CartService` to visualize the logic we have already built.