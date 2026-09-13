# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

Note: this value is a forced fallback, not a real fit. CB POS is a **native Qt/PyQt6 desktop app** (Windows-primary, developed cross-platform including on macOS) — it renders no HTML/CSS and has no browser-based live-iteration workflow. Impeccable's schema only recognizes `web`/`ios`/`android`/`adaptive`; none of those name a real desktop design language, so this project doesn't have a truthful value to record here. Treat any web-specific guidance (live mode, browser CSP/CDN rules, HTML/CSS craft-floor checks) as inapplicable to this project. The UI is styled via Qt Style Sheets (`cbpos/ui/styles/dark.qss` / `light.qss`), and structural work happens in PyQt widget code (`cbpos/ui/**/*.py`).

## Users

Non-technical shop owners and their 1-3 cashiers running small-to-medium retail businesses in Sri Lanka (grocery, pharmacy, hardware, clothing, and other retail categories). They self-install without IT support and learn the software through hands-on practice rather than manuals. Their job: run day-to-day retail operations — checkout/sales, inventory, customer/credit tracking, purchasing, and reporting — on modest Windows hardware, often with intermittent or no internet connectivity.

## Product Purpose

CB POS is free, closed-source point-of-sale software built to remove the cost and complexity barrier that keeps small Sri Lankan retailers from having real POS tooling. It exists to make professional-grade retail operations (fast checkout, inventory, tax compliance, reporting, multi-terminal sync) accessible to shop owners who can't afford commercial POS licenses or IT staff. Success means shops adopt it, run their daily operations reliably offline, and voluntarily promote it — the business model is reputation-based, not license revenue.

## Positioning

No single named competitor. CB POS's position is the combination of: genuinely free (not a trial or freemium tier), Sri Lanka-specific tax compliance handled correctly out of the box (backward VAT + SSCL calculation from MRP-inclusive shelf prices), full native trilingual support (Sinhala/English/Tamil) rather than English-only with translations bolted on, and zero-IT-department self-install/self-service operation. A neighboring product could copy any one of these but not the whole combination without also committing to giving the software away for free.

## Operating Context

- Runs on modest Windows PCs in small retail shops, often 1-3 terminals.
- Offline-first: a local SQLite database is the default. A shop may later opt into a shared network (PostgreSQL) database across terminals, or LAN Sync to keep separate per-terminal SQLite databases synced over a direct connection — these are mode switches, not the baseline.
- Interaction model is keyboard-first: cashiers work fast via keyboard shortcuts (F-keys; a barcode scanner is treated as keystroke input) for checkout speed. Touch-friendly affordances exist in the UI, but touch-friendliness is explicitly **not** a current design priority — keyboard-first speed comes first.
- Thermal receipt printing (ESC/POS, 58mm/80mm paper) is a core, frequently used output, alongside PDF/Excel reports and invoices.
- Cashiers may operate the software in a different language than the one printed for customers (e.g., an operator works in English but prints receipts in Sinhala or Tamil).
- Self-run: shop owners configure and troubleshoot the software themselves via a guided first-run Setup Wizard, not a support team.

## Capabilities and Constraints

- Money math: always `decimal.Decimal`, never `float`.
- Tax: shelf prices are MRP (tax-inclusive); VAT (18%) and SSCL (2.5% on 50% of revenue) are calculated backward from MRP, not added on top.
- Inventory costing: Weighted Average Cost (AVCO); quantities support 3 decimal places for weighed items.
- Critical actions (void, refund, price change) require permission checks and are written to an audit log.
- All customer-facing outputs (receipts, reports, invoices, PDFs, emails) must carry CB POS branding and website — a business-model requirement (reputation-based growth), not just a style choice.
- Every user-facing string goes through the i18n system (en/si/ta); no hardcoded English UI text.
- Hardware I/O (printing, emailing, heavy reports) must never block the main UI thread.
- Explicitly out of scope / removed from roadmap: gift cards, multi-location/multi-branch chain support, per-item multi-tax-rate schemes. This is single-shop software, not a multi-branch retail chain platform.
- Restaurant-specific workflows are a deferred future addon, not current scope.

## Brand Commitments

- Name: CB POS (Ceylon Byte POS). Branding and website must appear on all receipts, reports, invoices, PDFs, and emails the software produces.
- Documented dark/light theme palettes are an existing, durable visual commitment (see CLAUDE.md), not yet formally recorded in a DESIGN.md: dark theme — accent `#00BCEB` cyan, success `#39FF14` neon green, warning `#FFDC00`, destructive `#FF4136`, on `#1E1E1E`/`#252526` surfaces; light theme — accent `#0D6EFD` blue, success `#198754`, error `#DC3545`, on `#F8F9FA`/`#FFFFFF` surfaces.

## Evidence on Hand

- Seed/demo data exists for development and the first-run "Load Demo Data" option (80+ products, 15 customers, 8 suppliers, 30+ sample sales, three seeded roles: Admin/Manager/Cashier) — development and demo fixtures, not real customer evidence.
- No real customer testimonials, case studies, adoption numbers, or press exist; future design or copy work must not fabricate these.

## Product Principles

1. Zero-cost adoption over monetized features — the business model depends on shops being able to say yes with no budget conversation.
2. Correct-by-default compliance — Sri Lankan tax law (VAT/SSCL) and money math must be right without the shop owner having to understand the calculation.
3. Speed for the cashier over polish for the owner — the checkout path is optimized for keyboard-driven throughput; back-office screens can afford more explanatory chrome.
4. No assumed technical literacy — every screen must be learnable by a first-time, non-technical user without a manual or IT support.
5. Language is not an afterthought — Sinhala, Tamil, and English are peers, not English-plus-translation.

## Accessibility & Inclusion

Known, practical requirements rather than a formal standard (no WCAG or similar target has been established): full keyboard operability is the priority interaction model, especially for the checkout flow; touch-friendliness is present in the UI's affordances but is explicitly not a current design focus; the UI must stay legible and usable for non-technical, not-necessarily-English-fluent users across Sinhala, English, and Tamil.
