# Technical Design: Shop-Type Presets & Feature Flags Foundation (#942)

**Phase:** 10B · **Batch:** 10B.0  
**Issue:** #942 (Shop-type presets at first run and feature flags foundation) · **Epic:** #944  
**Decisions:** D34 (Phase 10B authorization, 7-shop preset matrix, wizard step placement, 'Other' minimal setup), D35 (Approved seeded-category matrix, localized `Category.name` storage Option A)  
**Date:** 2026-11-20  
**Status:** APPROVED (Post-EGM Review Applied)  

---

## 1. Context & Remediation Objectives

CB-POS is tailored for small Sri Lankan merchants across distinct trade sectors (grocery stores, pharmacies, hardware shops, clothing boutiques, phone/electronics repair and accessory shops, bookshops/stationeries, and bakeries). 

Prior to Phase 10B:
- Features were either universally enabled, or gated ad-hoc via `ConfigService` JSON settings (e.g. `warranty_enabled` checked `ConfigService.get("warranty_enabled")` or queried active policies).
- Setup wizard had no concept of shop categorization, forcing all shops into identical default configurations.
- Settings in `settings.json` are local to each terminal, preventing centralized multi-terminal configuration in network mode and LAN sync.

**Batch 10B.0 (#942)** builds the rock-solid foundation for all subsequent Phase 10B & 10C workflow features:
1. **Database-backed `feature_flags` table**: Shared across network mode, synced to tills via catalog sync, strictly read-only on tills.
2. **`FeatureFlags` Service & `feature_visible()` UI helper**: Centralized API with cached lookups, cache invalidation, mutation auditing, and `settings.features` permission gating.
3. **Preset Matrix & Seeding Engine**: 7 validated shop types + "Other", seeding flags, units, and approved top-level categories idempotently in the merchant's chosen language (Option A).
4. **Setup Wizard Tile Step**: Placed immediately after Shop Information, allowing merchants to choose their shop type visually with localized icon tiles.
5. **Settings → Features Page**: Interactive toggles for built features with one-line descriptions, `ReadOnlyBanner` on tills, and hiding unbuilt features until implemented.
6. **Integration of Pre-existing Features**: Hooking existing warranty, customer credit at checkout & management, cheque payments, and serial tracking to `FeatureFlags`.
7. **Sync Protocol Bump**: Minor bump to `1.6` with `feature_flags` included in `CATALOG_TABLES`, `CATALOG_DELETION_ORDER`, and `_TABLE_MODEL_MAP`.
8. **AST Guardrail**: Verifying no UI view attempts to read feature flags from `ConfigService`.

---

## 2. Elephant Pass: End-to-End System Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                ELEPHANT PASS: PHASE 10B.0 ARCHITECTURE                                │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                        │
│  [1. First-Run Setup Wizard Flow]                                                                      │
│      Step 1: Shop Information (Name, Address, Phone, VAT, Paper Width)                                 │
│      Step 2: Shop Type ("What kind of shop is this?")                                                  │
│              8 Large Icon Tiles: Grocery, Pharmacy, Hardware, Clothing, Phone & Electronics,          │
│              Bookshop, Bakery, Other. Subtitle: "You can change this anytime."                         │
│              Validation: Must select a shop type to proceed.                                           │
│      Step 3: Hardware (Receipt printer, A4 printer, Connection type)                                   │
│      Step 4: Security (Admin PIN)                                                                      │
│      * Wizard only collects shop_type; DB setup applies it (PIN ordering rule #791)                   │
│                                                                                                        │
│  [2. Database Initialization & Preset Application]                                                     │
│      main.py -> DatabaseSetupService.create_empty_database(admin_pin, shop_type)                       │
│      ├── Creates tables & stamps Alembic head                                                          │
│      ├── Seeds Core Data: Roles, Permissions, Admin User, Void Reasons, Payment Methods                │
│      └── Within the same transaction, calls FeatureFlags.apply_preset(shop_type, admin.id, session):   │
│          ├── 1. Feature Flags: Upserts 12 preset flags according to matrix into `feature_flags`        │
│          ├── 2. Units: Seeds missing units idempotently (pcs, kg, g, ft, m, tab, cap, btl, roll)      │
│          └── 3. Categories: Seeds approved top-level categories localized in Setup Wizard language     │
│      * Demo Database: scripts/seed.py applies the grocery or phone_electronics preset                  │
│        or turns on all IMPLEMENTED_FEATURES so demo data functions correctly.                         │
│                                                                                                        │
│  [3. Feature Flags Storage & Runtime Access]                                                           │
│      Database Table: `feature_flags(name PK, enabled BOOL, last_modified TIMESTAMP, updated_by INT FK)`│
│      Service: `FeatureFlags` (cbpos/core/services/feature_flags.py)                                    │
│      ├── is_on(name) -> bool (reads cached dict with RLock, refreshes from DB on miss or invalidate)   │
│      ├── set(name, bool, acting_user_id) -> audits, checks permission `settings.features`,             │
│      │   enforces `require_catalog_writable()` (fails on tills), invalidates cache                     │
│      ├── invalidate_cache() -> clears in-memory dictionary                                             │
│      └── UI Helper: `feature_visible(name) -> bool` (views call this, NEVER ConfigService)            │
│                                                                                                        │
│  [4. Multi-Terminal Sync (LAN Mode)]                                                                   │
│      Sync Protocol: 1.5 -> 1.6                                                                         │
│      CATALOG_TABLES includes "feature_flags"                                                           │
│      CATALOG_DELETION_ORDER includes "feature_flags" (before "users")                                  │
│      _TABLE_MODEL_MAP includes "feature_flags": FeatureFlag                                            │
│      Incremental pull: Uses `last_modified` index to pull changes since watermark                      │
│      Tills: Feature flags are read-only; when sync_client pulls "feature_flags", calls                 │
│      `FeatureFlags.invalidate_cache()` so the till UI updates immediately.                             │
│                                                                                                        │
│  [5. Settings UI & Management Navigation Gating]                                                        │
│      Settings -> Features Tab (`FeaturesPage`):                                                        │
│      ├── Only displays switches for features in `features.IMPLEMENTED_FEATURES`                        │
│      ├── Each switch shows translated feature name, 1-line explanation, and on/off status              │
│      ├── Gated on `settings.features` or `admin.settings`                                              │
│      └── If `catalog_is_read_only()`, renders `ReadOnlyBanner` and disables toggles                    │
│      UI Gating Integration:                                                                            │
│      ├── ManagementView:                                                                               │
│      │   - `credit_book`: Hidden if not feature_visible(Features.CREDIT_BOOK)                          │
│      │   - `warranty`: Hidden if not feature_visible(Features.WARRANTY)                                 │
│      ├── Checkout / PaymentDialog & PaymentService:                                                    │
│      │   - Credit method: Omitted if not feature_visible(Features.CREDIT_BOOK)                         │
│      │   - Cheque method: Omitted if not feature_visible(Features.CHEQUES)                             │
│      └── ProductEditor:                                                                                │
│          - Serial/IMEI checkbox: Omitted if not feature_visible(Features.SERIAL_TRACKING)              │
│                                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Goldfish Pass: Detailed Invariants & Components

### 3.1 Preset Matrix Specification

Approved preset matrix (Decision D34):
- `ON`: Enabled by default upon applying preset.
- `off`: Disabled by default upon applying preset.
- `optional`: Disabled by default (`False`), but available to be toggled in Settings → Features.
- `Other`: All optional features OFF; ensures standard `pcs` unit exists; zero categories seeded.

Constants defined in `cbpos/core/constants/features.py`:
```python
class ShopTypes:
    GROCERY = "grocery"
    PHARMACY = "pharmacy"
    HARDWARE = "hardware"
    CLOTHING = "clothing"
    PHONE_ELECTRONICS = "phone_electronics"
    BOOKSHOP = "bookshop"
    BAKERY = "bakery"
    OTHER = "other"


class Features:
    EXPIRY_DATES = "expiry_dates"
    BATCHES = "batches"
    WEIGHT_SCALE = "weight_scale"
    PRICE_BOARD = "price_board"
    CREDIT_BOOK = "credit_book"
    CHEQUES = "cheques"
    SERIAL_TRACKING = "serial_tracking"
    VARIANTS = "variants"
    QUOTATIONS = "quotations"
    UNIT_CONVERSION = "unit_conversion"
    DEPOSITS = "deposits"
    WARRANTY = "warranty"


IMPLEMENTED_FEATURES = {
    Features.WARRANTY,
    Features.CREDIT_BOOK,
    Features.SERIAL_TRACKING,
    Features.CHEQUES,
}
```

| Feature Name Constant | Grocery | Pharmacy | Hardware | Clothing | Phone/Elec | Bookshop | Bakery | Other | Status in Codebase |
|---|---|---|---|---|---|---|---|---|---|
| `Features.EXPIRY_DATES` | optional (`False`) | **ON** (`True`) | off (`False`) | off (`False`) | off (`False`) | off (`False`) | **ON** (`True`) | off | Planned (10B.4 #926) |
| `Features.BATCHES` | **ON** (`True`) | **ON** (`True`) | off (`False`) | off (`False`) | off (`False`) | off (`False`) | off (`False`) | off | Planned (10B.4 #926) |
| `Features.WEIGHT_SCALE` | **ON** (`True`) | off (`False`) | **ON** (`True`) | off (`False`) | off (`False`) | off (`False`) | **ON** (`True`) | off | Planned (Hardware) |
| `Features.PRICE_BOARD` | **ON** (`True`) | off (`False`) | **ON** (`True`) | off (`False`) | off (`False`) | off (`False`) | **ON** (`True`) | off | Planned (10B.2 #931) |
| `Features.CREDIT_BOOK` | **ON** (`True`) | **ON** (`True`) | **ON** (`True`) | off (`False`) | **ON** (`True`) | **ON** (`True`) | off (`False`) | off | **IMPLEMENTED** (Phase 3A) |
| `Features.CHEQUES` | off (`False`) | **ON** (`True`) | **ON** (`True`) | off (`False`) | **ON** (`True`) | **ON** (`True`) | off (`False`) | off | **IMPLEMENTED** (PaymentMethod) / Planned (10C) |
| `Features.SERIAL_TRACKING`| off (`False`) | off (`False`) | optional (`False`)| off (`False`) | **ON** (`True`) | off (`False`) | off (`False`) | off | **IMPLEMENTED** (Phase 9 #823) |
| `Features.VARIANTS` | off (`False`) | off (`False`) | off (`False`) | **ON** (`True`) | optional (`False`)| off (`False`) | off (`False`) | off | Planned (10B.6 #936) |
| `Features.QUOTATIONS` | off (`False`) | off (`False`) | **ON** (`True`) | off (`False`) | **ON** (`True`) | **ON** (`True`) | **ON** (`True`) | off | Planned (10C #935) |
| `Features.UNIT_CONVERSION`| **ON** (`True`) | **ON** (`True`) | **ON** (`True`) | off (`False`) | off (`False`) | off (`False`) | off (`False`) | off | Planned (10B.3 #937) |
| `Features.DEPOSITS` | optional (`False`)| off (`False`) | off (`False`) | off (`False`) | off (`False`) | off (`False`) | off (`False`) | off | Planned (10B.7 #941) |
| `Features.WARRANTY` | off (`False`) | off (`False`) | optional (`False`)| off (`False`) | **ON** (`True`) | off (`False`) | off (`False`) | off | **IMPLEMENTED** (Phase 9 #820-#830) |

### 3.2 Unit Seeding per Preset

Units seeded per preset from issue #942:
- **Grocery**: `kg`, `g`, `pcs`, `pk`
- **Pharmacy**: `tab`, `cap`, `btl`, `pcs`
- **Hardware**: `ft`, `m`, `pcs`, `kg`, `roll`
- **Clothing**: `pcs`
- **Phone & Electronics**: `pcs`
- **Bookshop**: `pcs`
- **Bakery**: `pcs`, `kg`
- **Other**: `pcs`

Unit canonical definitions:
- `pcs`: Name="Piece", Abbreviation="pcs", Decimals=0
- `kg`: Name="Kilogram", Abbreviation="kg", Decimals=3
- `g`: Name="Gram", Abbreviation="g", Decimals=0
- `pk`: Name="Pack", Abbreviation="pk", Decimals=0
- `m`: Name="Meter", Abbreviation="m", Decimals=2
- `ft`: Name="Foot", Abbreviation="ft", Decimals=2
- `tab`: Name="Tablet", Abbreviation="tab", Decimals=0
- `cap`: Name="Capsule", Abbreviation="cap", Decimals=0
- `btl`: Name="Bottle", Abbreviation="btl", Decimals=0
- `roll`: Name="Roll", Abbreviation="roll", Decimals=0

Deduplication: Check both abbreviation and name to prevent `IntegrityError` against `Unit.name` unique constraint:
```python
existing = (
    session.query(Unit)
    .filter((func.lower(Unit.abbreviation) == abbr.lower()) | (func.lower(Unit.name) == name.lower()))
    .first()
)
```

### 3.3 Seeded Categories per Preset (Decision D35)

Categories are seeded based on the active language selected during Step 1 of the Setup Wizard:
- If `si`: Seed Sinhala names.
- If `ta`: Seed Tamil names.
- Else: Seed English names.

Categories are strictly top-level (`parent_id=None`).
Deduplication:
```python
existing = session.query(Category).filter(func.lower(Category.name) == name.strip().lower()).first()
```
If exists, skip.

Approved category mappings:
```python
PRESET_CATEGORIES = {
    "grocery": [
        {"en": "Food & Provisions", "si": "ආහාර සහ ද්‍රව්‍ය", "ta": "உணவுப் பொருட்கள்", "color": "#FF9800"},
        {"en": "Beverages", "si": "බීම වර්ග", "ta": "பானங்கள்", "color": "#00BCEB"},
        {
            "en": "Snacks & Confectionery",
            "si": "කෙටි කෑම සහ රසකැවිලි",
            "ta": "சிற்றுண்டிகள் மற்றும் இனிப்புகள்",
            "color": "#FFD700",
        },
        {"en": "Household & Cleaning", "si": "ගෘහ සහ පිරිසිදුකාරක", "ta": "வீட்டுப் பராமரிப்பு பொருட்கள்", "color": "#9C27B0"},
        {"en": "Personal Care", "si": "පුද්ගලික සත්කාර", "ta": "தனிநபர் பராமரிப்பு", "color": "#E91E63"},
    ],
    "pharmacy": [
        {
            "en": "Prescription Medicines",
            "si": "බෙහෙත් වට්ටෝරු ඖෂධ",
            "ta": "மருத்துவர் பரிந்துரை மருந்துகள்",
            "color": "#F44336",
        },
        {"en": "Over The Counter", "si": "සාමාන්‍ය ඖෂධ (OTC)", "ta": "பொது மருந்துகள்", "color": "#4CAF50"},
        {"en": "Wellness & Supplements", "si": "සුවතා සහ අතිරේක", "ta": "ஆரோக்கியம் மற்றும் சத்துணவு", "color": "#00BCD4"},
        {
            "en": "Medical Devices & First Aid",
            "si": "වෛද්‍ය උපකරණ සහ ප්‍රථමාධාර",
            "ta": "மருத்துவ உபகரணங்கள் மற்றும் முதலுதவி",
            "color": "#2196F3",
        },
    ],
    "hardware": [
        {"en": "Building & Masonry", "si": "ඉදිකිරීම් ද්‍රව්‍ය", "ta": "கட்டடப் பொருட்கள்", "color": "#795548"},
        {"en": "Plumbing & Sanitary", "si": "නල සහ සනීපාරක්ෂක", "ta": "குழாய் மற்றும் சுகாதாரப் பொருட்கள்", "color": "#03A9F4"},
        {"en": "Electrical & Lighting", "si": "විදුලි සහ ආලෝකකරණ", "ta": "மின்சாரம் மற்றும் விளக்குகள்", "color": "#FFC107"},
        {"en": "Tools & Fasteners", "si": "මෙවලම් සහ ඇණ/මුරිච්චි", "ta": "கருவிகள் மற்றும் திருகுகள்", "color": "#607D8B"},
        {"en": "Paints & Solvents", "si": "තීන්ත සහ ද්‍රාවක", "ta": "வண்ணங்கள் மற்றும் கரைප්பான்கள்", "color": "#E91E63"},
    ],
    "clothing": [
        {"en": "Men's Wear", "si": "පිරිමි ඇඳුම්", "ta": "ஆண்கள் ஆடை", "color": "#3F51B5"},
        {"en": "Women's Wear", "si": "කාන්තා ඇඳුම්", "ta": "பெண்கள் ஆடை", "color": "#E91E63"},
        {"en": "Kids' Wear", "si": "ළමා ඇඳුම්", "ta": "குழந்தைகள் ஆடை", "color": "#4CAF50"},
        {"en": "Accessories & Footwear", "si": "උපාංග සහ පාවහන්", "ta": "பாகங்கள் மற்றும் பாதணிகள்", "color": "#FF9800"},
    ],
    "phone_electronics": [
        {"en": "Mobile Phones & Tablets", "si": "ජංගම දුරකථන සහ ටැබ්ලට්", "ta": "கையடக்கத் தொலைபேசிகள்", "color": "#2196F3"},
        {"en": "Audio & Accessories", "si": "ශ්‍රව්‍ය සහ උපාංග", "ta": "ஆடியோ மற்றும் பாகங்கள்", "color": "#9C27B0"},
        {"en": "Parts & Protection", "si": "අමතර කොටස් සහ ආරක්ෂණ", "ta": "உதிரிப்பாகங்கள் மற்றும் பாதுகாப்பு", "color": "#607D8B"},
        {"en": "Small Appliances", "si": "කුඩා විදුලි උපකරණ", "ta": "சிறிய வீட்டு உபயோகப் பொருட்கள்", "color": "#FF5722"},
    ],
    "bookshop": [
        {"en": "Books & Publications", "si": "පොත් සහ ප්‍රකාශන", "ta": "புத்தகங்கள் மற்றும் வெளியீடுகள்", "color": "#8D6E63"},
        {
            "en": "School & Office Stationery",
            "si": "පාසල් සහ කාර්යාල ලිපිද්‍රව්‍ය",
            "ta": "பள்ளி மற்றும் அலுவலக எழுதுபொருட்கள்",
            "color": "#009688",
        },
        {"en": "Art & Craft Supplies", "si": "චිත්‍ර සහ නිර්මාණ ද්‍රව්‍ය", "ta": "கலை மற்றும் கைவினைப் பொருட்கள்", "color": "#E91E63"},
        {"en": "Paper & Printing", "si": "කඩදාසි සහ මුද්‍රණ", "ta": "காகிதம் மற்றும் அச்சிடுதல்", "color": "#3F51B5"},
    ],
    "bakery": [
        {"en": "Bread & Buns", "si": "පාන් සහ බනිස්", "ta": "பாண் மற்றும் பன்கள்", "color": "#FF9800"},
        {"en": "Pastries & Savouries", "si": "පේස්ට්‍රි සහ සැර කෑම", "ta": "பேஸ்ட்ரிகள் மற்றும் கார வகைகள்", "color": "#FF5722"},
        {"en": "Cakes & Sweets", "si": "කේක් සහ රසකැවිලි", "ta": "கேக் மற்றும் இனிப்புகள்", "color": "#E91E63"},
        {"en": "Beverages", "si": "බීම වර්ග", "ta": "பானங்கள்", "color": "#00BCD4"},
    ],
    "other": [],
}
```

### 3.4 Database Schema & Migration

New model `FeatureFlag` in `cbpos/core/models/feature_flag.py`:
```python
class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    user: Mapped[Optional["User"]] = relationship()
```

Alembic migration:
- Revision: generated hash, depends on `c5d6e7f8a9b0`.
- Creates `feature_flags` table with SQLite & PostgreSQL compatibility.
- Reversible `downgrade()`.

### 3.5 Permissions & Audit

In `cbpos/core/constants/permissions.py`:
- `SETTINGS_FEATURES = "settings.features"`
- Added to `Admin` group and `SETTINGS_PAGE_PERMISSIONS["features"] = (Permissions.SETTINGS_FEATURES, Permissions.ADMIN_SETTINGS)`.
- Automatically granted to `Admin` role in `DatabaseSetupService`.

In `cbpos/core/constants/audit.py`:
- `FEATURE_FLAG_EVENT = "FEATURE_FLAGS"`
- Audit log entry written whenever a flag is toggled or a preset is applied:
  - Event Type: `FEATURE_FLAGS`
  - Action: `SET_FEATURE_FLAG` or `APPLY_SHOP_PRESET`
  - Details: `json.dumps({"flag": name, "enabled": enabled, "old_enabled": ...})` or `json.dumps({"shop_type": shop_type, "flags": ...})`

### 3.6 Multi-Terminal LAN Sync Integration

In `cbpos/core/services/sync_protocol.py`:
- `SYNC_PROTOCOL_VERSION = "1.6"`
- `CATALOG_TABLES`: Append `"feature_flags"`.
- `CATALOG_DELETION_ORDER`: Insert `"feature_flags"` before `"users"` (because of `updated_by` FK).
- `_TABLE_MODEL_MAP`: Map `"feature_flags": FeatureFlag`.

In `cbpos/infrastructure/sync_client.py`:
- In `_apply_catalog_pull()`, after committing changes for `"feature_flags"`, call:
  ```python
  from cbpos.core.services.feature_flags import FeatureFlags

  FeatureFlags.invalidate_cache()
  ```
  This guarantees tills immediately see flag updates performed on the Main PC without restarting the application.

### 3.7 Invariant Proofs

1. **Fresh DB Invariant**: A fresh DB created without applying a preset has no rows in `feature_flags`. `FeatureFlags.is_on(name)` returns `False` for any flag.
2. **Preset Invariant**: Applying a preset sets exactly the 12 approved matrix flags. Re-applying is completely idempotent.
3. **Till Read-Only Invariant**: Calling `FeatureFlags.set(...)` or `FeatureFlags.apply_preset(...)` on a till (`terminal_mode == "terminal"`) raises `CatalogReadOnlyError`.
4. **AST Architecture Invariant**: No UI view reads `features.*` from `ConfigService`. Guardrail test parses AST of all `cbpos/ui/**/*.py` files and fails if any `ConfigService.get` or `ConfigService.set` uses a key starting with `features.` or `feature.`.
5. **UI Gating Invariants**:
   - `ManagementView`: Warranty tab hidden when `not feature_visible(Features.WARRANTY)`; Credit Book tab hidden when `not feature_visible(Features.CREDIT_BOOK)`.
   - `PaymentDialog` / `PaymentService`: Credit payment button/method omitted when `not feature_visible(Features.CREDIT_BOOK)`; Cheque button/method omitted when `not feature_visible(Features.CHEQUES)`.
   - `ProductEditor`: Serial/IMEI tracking checkbox omitted when `not feature_visible(Features.SERIAL_TRACKING)`.

---

## 4. UI Gate & Impeccable Plan

### 4.1 Setup Wizard Step ("What kind of shop is this?")
- Placed between Step 1 (Shop Info) and Step 3 (Hardware).
- Title: "What kind of shop is this?" / "මෙය කුමන ආකාරයේ කඩයක්ද?" / "இது என்ன வகையான கடை?"
- Subtitle: "You can change this anytime." / "ඔබට මෙය පසුව ඕනෑම වේලාවක වෙනස් කළ හැක." / "இதை நீங்கள் பின்னர் எப்போது வேண்டுமானாலும் மாற்றலாம்."
- 8 large clickable card tiles arranged in a clean 4×2 grid:
  - Tile 1: Grocery (`ShopTypes.GROCERY`)
  - Tile 2: Pharmacy (`ShopTypes.PHARMACY`)
  - Tile 3: Hardware (`ShopTypes.HARDWARE`)
  - Tile 4: Clothing (`ShopTypes.CLOTHING`)
  - Tile 5: Phone & Electronics (`ShopTypes.PHONE_ELECTRONICS`)
  - Tile 6: Bookshop (`ShopTypes.BOOKSHOP`)
  - Tile 7: Bakery (`ShopTypes.BAKERY`)
  - Tile 8: Other (`ShopTypes.OTHER`)
- Validation: Next button validates that a shop type has been selected, alerting `setup_wizard.shop_type_required` if none selected.
- Visual active state: primary accent border, selected check badge, subtle elevation.
- Fully keyboard accessible (Arrow keys, Tab, Enter/Space to select).

### 4.2 Settings → Features Page (`FeaturesPage`)
- Added to Settings sidebar: "Features" / "විශේෂාංග" / "அம்சங்கள்" with a slider/toggle icon.
- Cards for each implemented feature in `features.IMPLEMENTED_FEATURES`:
  - Warranty & Repairs (`Features.WARRANTY`)
  - Customer Credit Book (`Features.CREDIT_BOOK`)
  - Serial & IMEI Tracking (`Features.SERIAL_TRACKING`)
  - Cheque Payments (`Features.CHEQUES`)
- Each card contains:
  - Feature name (Bold)
  - 1-line plain-language explanation of what turning it on/off does
  - Animated ToggleSwitch (green ON / neutral OFF)
  - Instant save with audit logging and toast notice
- Till Behavior: If `catalog_is_read_only()`, renders `ReadOnlyBanner` at the top and disables all toggle switches.
- Unimplemented features from the matrix are strictly omitted from the page.

---

## 5. Verification Plan

1. **Focused Unit Tests**:
   - `test_feature_flags_service.py`: `is_on()`, `set()`, `apply_preset()`, caching, invalidation, audit logging, permissions, till read-only block.
   - `test_preset_seeding.py`: 8 presets tested for correct 12 flags, unit deduplication, and category seeding across EN/SI/TA.
   - `test_sync_feature_flags.py`: `feature_flags` serialization, pull-catalog inclusion, incremental pull via `last_modified`, till cache invalidation.
   - `test_feature_gating_ui.py`: UI gating across `ManagementView`, `PaymentDialog`, `PaymentService`, and `ProductEditor`.
2. **AST Guardrail**:
   - `test_views_never_read_features_from_config_service()` in `test_architecture_rules.py`.
3. **UI Gate**:
   - Impeccable review of Setup Wizard tiles and Settings Features page.
   - Screenshots captured at 1366×768 in Dark and Light themes across English, Sinhala, and Tamil.
4. **Full Test Suite & Lint**:
   - `uv run pre-commit run --all-files`
   - `QT_QPA_PLATFORM=offscreen uv run python -m pytest -q -n auto`
