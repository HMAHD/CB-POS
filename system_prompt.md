# PROJECT CONTEXT: CB POS (Ceybyte.com)

## 1. Project Overview
- **Name:** CB POS
- **Developer:** Ceybyte.com
- **Tech Stack:** .NET 8/9, WinUI 3 (Windows App SDK), Entity Framework Core (SQLite/SQL Server), CommunityToolkit.Mvvm.
- **Target Audience:** Sri Lankan retailers (Sinhala, Tamil, English support required).

## 2. Coding Philosophy: "Industrial & Simple"
- **Architecture:** Modular Monolith using Clean Architecture (Presentation -> Application -> Domain <- Infrastructure).
- **Modularity:** Features must be isolated in separate namespaces/folders (e.g., `Features.Sales`, `Features.Inventory`).
- **Comments:** XML documentation for all public methods. Inline comments for complex logic only.
- **Naming Conventions:** - Classes: PascalCase (e.g., `ProductService`)
  - Private Fields: _camelCase (e.g., `_printerService`)
  - Methods: Verb-Noun (e.g., `CalculateTax`, `PrintReceipt`)
  - **Rule:** NO abbreviations. Use `TransactionRepository`, NOT `TransRepo`.

## 3. Critical Requirements
- **UX:** Interface must be touch-friendly, high contrast, and minimalistic. No complex menus.
- **Localization:** All UI strings must use `x:Uid` and `.resw` files to support Sinhala (SI-LK), Tamil (TA-LK), and English (EN-US).
- **Hardware:** Hardware interaction (Printers/Scanners) must be behind Interfaces (`IPrinterService`) to allow swapping hardware without breaking the UI.
- **Error Handling:** Global Exception Handling required. Logs must be written to local files (Serilog).

## 4. AI & Future Proofing
- Code must be SOLID. 
- Use Dependency Injection for EVERYTHING.
- Leave "Hooks" for AI features (e.g., `IRecommendationEngine` interfaces) even if implementing later.

