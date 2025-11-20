# CB POS - Architecture Overview
- **Core:** Contains Domain Entities (Product, Sale) and Interfaces (IPrinterService). Pure C#.
- **Infrastructure:** Contains EF Core DbContext, Hardware Implementations (EscPosPrinter).
- **UI:** WinUI 3. Uses Dependency Injection via App.xaml.cs.
- **Localization:** Strings located in Strings/si-LK, ta-LK, en-US.
