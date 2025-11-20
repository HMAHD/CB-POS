# CB POS Solution Scaffolding Script
# Stack: .NET 9, WinUI 3, SQLite, Serilog, Clean Architecture

Write-Host "🚀 Initializing CB POS (Industrial Grade)..." -ForegroundColor Cyan

# 1. Create Solution
dotnet new sln -n "CB.POS"

# 2. Create Projects (Clean Architecture)
# Core: Entities, Interfaces, DTOs (No dependencies on UI or DB)
dotnet new classlib -n "CB.POS.Core" -f net9.0
# Infrastructure: Database, Printer implementations, External APIs
dotnet new classlib -n "CB.POS.Infrastructure" -f net9.0
# UI: The WinUI 3 Application
dotnet new winui -n "CB.POS.UI" -f net9.0

# 3. Define Project References
# UI depends on Core and Infrastructure
dotnet add "CB.POS.UI/CB.POS.UI.csproj" reference "CB.POS.Core/CB.POS.Core.csproj"
dotnet add "CB.POS.UI/CB.POS.UI.csproj" reference "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj"
# Infrastructure depends on Core
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" reference "CB.POS.Core/CB.POS.Core.csproj"

# 4. Add Solution Folders & Link Projects
dotnet sln "CB.POS.sln" add "CB.POS.Core/CB.POS.Core.csproj" --solution-folder "1. Core"
dotnet sln "CB.POS.sln" add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" --solution-folder "2. Infrastructure"
dotnet sln "CB.POS.sln" add "CB.POS.UI/CB.POS.UI.csproj" --solution-folder "3. Presentation"

# 5. Create Industrial Folder Structure (Modular)
$folders = @(
    "CB.POS.Core/Entities",
    "CB.POS.Core/Interfaces/Hardware",
    "CB.POS.Core/Interfaces/Services",
    "CB.POS.Core/Interfaces/Repositories",
    "CB.POS.Core/Features/Sales",
    "CB.POS.Core/Features/Inventory",
    
    "CB.POS.Infrastructure/Data",
    "CB.POS.Infrastructure/Hardware/Printers",
    "CB.POS.Infrastructure/Hardware/Scanners",
    "CB.POS.Infrastructure/Services",
    
    "CB.POS.UI/Services",
    "CB.POS.UI/ViewModels",
    "CB.POS.UI/Views/Sales",
    "CB.POS.UI/Views/Admin",
    "CB.POS.UI/Strings/en-US",
    "CB.POS.UI/Strings/si-LK",
    "CB.POS.UI/Strings/ta-LK"
)

foreach ($folder in $folders) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
}

# 6. Install Critical NuGets (The "Industrial" Stack)
Write-Host "📦 Installing Industrial Grade Packages..." -ForegroundColor Yellow

# Core: MVVM Toolkit (Standard for WinUI)
dotnet add "CB.POS.Core/CB.POS.Core.csproj" package CommunityToolkit.Mvvm

# Infrastructure: EF Core SQLite, Serilog (Logging), ESCPOS (Printing)
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" package Microsoft.EntityFrameworkCore.Sqlite
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" package Microsoft.EntityFrameworkCore.Tools
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" package Serilog.Extensions.Logging.File
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" package ESC-POS-NET

# CB POS Solution Scaffolding Script
# Stack: .NET 9, WinUI 3, SQLite, Serilog, Clean Architecture

Write-Host "🚀 Initializing CB POS (Industrial Grade)..." -ForegroundColor Cyan

# 1. Create Solution
dotnet new sln -n "CB.POS"

# 2. Create Projects (Clean Architecture)
# Core: Entities, Interfaces, DTOs (No dependencies on UI or DB)
dotnet new classlib -n "CB.POS.Core" -f net9.0
# Infrastructure: Database, Printer implementations, External APIs
dotnet new classlib -n "CB.POS.Infrastructure" -f net9.0
# UI: The WinUI 3 Application
dotnet new winui -n "CB.POS.UI" -f net9.0

# 3. Define Project References
# UI depends on Core and Infrastructure
dotnet add "CB.POS.UI/CB.POS.UI.csproj" reference "CB.POS.Core/CB.POS.Core.csproj"
dotnet add "CB.POS.UI/CB.POS.UI.csproj" reference "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj"
# Infrastructure depends on Core
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" reference "CB.POS.Core/CB.POS.Core.csproj"

# 4. Add Solution Folders & Link Projects
dotnet sln "CB.POS.sln" add "CB.POS.Core/CB.POS.Core.csproj" --solution-folder "1. Core"
dotnet sln "CB.POS.sln" add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" --solution-folder "2. Infrastructure"
dotnet sln "CB.POS.sln" add "CB.POS.UI/CB.POS.UI.csproj" --solution-folder "3. Presentation"

# 5. Create Industrial Folder Structure (Modular)
$folders = @(
    "CB.POS.Core/Entities",
    "CB.POS.Core/Interfaces/Hardware",
    "CB.POS.Core/Interfaces/Services",
    "CB.POS.Core/Interfaces/Repositories",
    "CB.POS.Core/Features/Sales",
    "CB.POS.Core/Features/Inventory",
    
    "CB.POS.Infrastructure/Data",
    "CB.POS.Infrastructure/Hardware/Printers",
    "CB.POS.Infrastructure/Hardware/Scanners",
    "CB.POS.Infrastructure/Services",
    
    "CB.POS.UI/Services",
    "CB.POS.UI/ViewModels",
    "CB.POS.UI/Views/Sales",
    "CB.POS.UI/Views/Admin",
    "CB.POS.UI/Strings/en-US",
    "CB.POS.UI/Strings/si-LK",
    "CB.POS.UI/Strings/ta-LK"
)

foreach ($folder in $folders) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
}

# 6. Install Critical NuGets (The "Industrial" Stack)
Write-Host "📦 Installing Industrial Grade Packages..." -ForegroundColor Yellow

# Core: MVVM Toolkit (Standard for WinUI)
dotnet add "CB.POS.Core/CB.POS.Core.csproj" package CommunityToolkit.Mvvm

# Infrastructure: EF Core SQLite, Serilog (Logging), ESCPOS (Printing)
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" package Microsoft.EntityFrameworkCore.Sqlite
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" package Microsoft.EntityFrameworkCore.Tools
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" package Serilog.Extensions.Logging.File
dotnet add "CB.POS.Infrastructure/CB.POS.Infrastructure.csproj" package ESC-POS-NET

# UI: Dependency Injection, Behaviors (for Keyboard Hooks)
dotnet add "CB.POS.UI/CB.POS.UI.csproj" package Microsoft.Extensions.Hosting
dotnet add "CB.POS.UI/CB.POS.UI.csproj" package Microsoft.Extensions.DependencyInjection
dotnet add "CB.POS.UI/CB.POS.UI.csproj" package Microsoft.Xaml.Behaviors.WinUI.Managed

# 7. Create a Dummy "ReadMe" for AI Context
$readmeContent = @"
# CB POS - Architecture Overview
- **Core:** Contains Domain Entities (Product, Sale) and Interfaces (IPrinterService). Pure C#.
- **Infrastructure:** Contains EF Core DbContext, Hardware Implementations (EscPosPrinter).
- **UI:** WinUI 3. Uses Dependency Injection via App.xaml.cs.
- **Localization:** Strings located in Strings/si-LK, ta-LK, en-US.
"@
Set-Content -Path "Architecture.md" -Value $readmeContent

Write-Host "✅ CB POS Scaffolding Complete! Open CB.POS.sln in Visual Studio." -ForegroundColor Green