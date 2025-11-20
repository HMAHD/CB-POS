# CB POS - Point of Sale System

<div align="center">

**Industrial-Grade POS Solution for Sri Lankan Retailers**

[![.NET](https://img.shields.io/badge/.NET-9.0-512BD4?logo=dotnet)](https://dotnet.microsoft.com/)
[![WinUI 3](https://img.shields.io/badge/WinUI-3-0078D4?logo=windows)](https://learn.microsoft.com/windows/apps/winui/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](#license)

*Developed by [Ceybyte.com](https://ceybyte.com)*

</div>

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Build Instructions](#build-instructions)
- [Project Structure](#project-structure)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Localization](#localization)
- [Hardware Integration](#hardware-integration)
- [Development Guidelines](#development-guidelines)
- [AI Roadmap](#ai-roadmap)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## 🎯 Overview

**CB POS** is a modern, industrial-grade Point of Sale system specifically designed for Sri Lankan retail environments. Built with the "Industrial & Simple" philosophy, it combines enterprise-level architecture with an intuitive, keyboard-first interface optimized for high-speed cashier operations.

### Key Highlights

- ✅ **Multi-language Support**: Sinhala, Tamil, and English with proper Unicode rendering
- ✅ **Keyboard-First Design**: Every action accessible via hotkeys for maximum cashier efficiency
- ✅ **Hardware Integration**: Direct ESC/POS printer control, barcode scanner support, cash drawer integration
- ✅ **Unpackaged Deployment**: No sandbox restrictions - full hardware and file system access
- ✅ **Clean Architecture**: Modular, testable, and maintainable codebase following SOLID principles
- ✅ **Offline-First**: SQLite database with optional SQL Server support

---

## ✨ Features

### Core Functionality
- **Point of Sale**: Fast, keyboard-driven checkout process
- **Inventory Management**: Real-time stock tracking with low-stock alerts
- **Product Management**: Barcode-based product lookup and manual search
- **Transaction Management**: Hold/recall bills, void items, price checks
- **Reporting**: Daily sales, X-Read/Z-Read reports
- **Multi-currency**: LKR (Rs.) formatting with proper localization

### User Experience
- **Touch-Friendly**: Large hit targets (48x48px minimum) for non-cashier interactions
- **Focus-Aggressive**: Cursor automatically returns to barcode input after every action
- **Visual Hotkey Indicators**: All buttons display their keyboard shortcuts
- **High Contrast**: Optimized for retail environments with varying lighting

### Security
- **Role-Based Access**: Manager functions require PIN authentication
- **Session Management**: Lock/logout functionality (F12)
- **Audit Logging**: Comprehensive transaction logging with Serilog

---

## 🏗️ Architecture

CB POS follows **Clean Architecture** principles with a modular monolith approach:

```
┌─────────────────────────────────────────┐
│           CB.POS.UI (WinUI 3)           │
│  ┌─────────────────────────────────┐   │
│  │  Views (XAML)                   │   │
│  │  ViewModels (MVVM)              │   │
│  │  Services (Navigation, Focus)   │   │
│  └─────────────────────────────────┘   │
└──────────────┬──────────────────────────┘
               │ Dependency Injection
┌──────────────┴──────────────────────────┐
│         CB.POS.Infrastructure           │
│  ┌─────────────────────────────────┐   │
│  │  Data (EF Core, SQLite)         │   │
│  │  Hardware (Printer, Scanner)    │   │
│  │  Services (Implementations)     │   │
│  └─────────────────────────────────┘   │
└──────────────┬──────────────────────────┘
               │ Interfaces
┌──────────────┴──────────────────────────┐
│            CB.POS.Core                  │
│  ┌─────────────────────────────────┐   │
│  │  Entities (Product, Sale, etc.) │   │
│  │  Interfaces (IPrinterService)   │   │
│  │  DTOs (Data Transfer Objects)   │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Layer Responsibilities

- **Core**: Pure C# domain logic, entities, and interface definitions
- **Infrastructure**: Database access, hardware implementations, external services
- **UI**: WinUI 3 presentation layer with MVVM pattern

---

## 🛠️ Technology Stack

| Category | Technology | Version |
|----------|-----------|---------|
| **Framework** | .NET | 9.0 |
| **UI Framework** | WinUI 3 (Windows App SDK) | 1.6 |
| **MVVM Toolkit** | CommunityToolkit.Mvvm | 8.3.2 |
| **Database** | Entity Framework Core + SQLite | 9.0 |
| **Logging** | Serilog | 4.1.0 |
| **DI Container** | Microsoft.Extensions.DependencyInjection | 9.0 |
| **Hosting** | Microsoft.Extensions.Hosting (Generic Host) | 9.0 |

### Hardware Libraries
- **Thermal Printers**: ESC/POS commands (Raw socket/USB)
- **Barcode Scanners**: HID mode / SerialPort
- **Cash Drawer**: Triggered via printer RJ11 signal

---

## 📦 Prerequisites

### Required Software
- **Operating System**: Windows 10 (19041) or later
- **.NET SDK**: 9.0.308 or later
- **Visual Studio**: 2022/2025 Preview with:
  - Desktop development with C++
  - Windows App SDK (WinUI) workload
  - .NET desktop development

### Recommended Fonts (for Sinhala/Tamil)
- **Iskoola Pota** (Sinhala)
- **Nirmala UI** (Tamil/Sinhala fallback)

---

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/ceybyte/CB-POS.git
cd CB-POS
```

### 2. Restore Dependencies
```bash
dotnet restore
```

### 3. Initialize Database
The database will be automatically created on first run at:
```
%LOCALAPPDATA%\CB_POS\cbpos.db
```

Default admin user:
- **Name**: Super Admin
- **PIN**: 1234
- **Role**: Admin

---

## 🔨 Build Instructions

### Option 1: Visual Studio (Recommended)
1. Open `CB.POS.slnx` in Visual Studio 2022/2025
2. Set `CB.POS.UI` as the startup project
3. Press **F5** or **Ctrl+Shift+B** to build and run

### Option 2: Command Line (MSBuild)
```powershell
# Build using Visual Studio's MSBuild
& "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" `
  CB.POS.UI\CB.POS.UI.csproj /t:Build /p:Configuration=Debug /p:Platform=x64

# Run the application
.\CB.POS.UI\bin\x64\Debug\net9.0-windows10.0.19041.0\CB.POS.UI.exe
```

> **⚠️ Important**: Use Visual Studio's MSBuild, not `dotnet build`. See [Troubleshooting](#troubleshooting) for details.

### Build Configuration
The project is configured for **unpackaged deployment**:
```xml
<WindowsPackageType>None</WindowsPackageType>
<WindowsAppSDKSelfContained>true</WindowsAppSDKSelfContained>
<Platform>x64</Platform>
```

This provides:
- Direct hardware access (no sandbox)
- Standard .exe deployment
- Full file system access
- Better printer/scanner integration

---

## 📁 Project Structure

```
CB-POS/
├── CB.POS.Core/                    # Domain Layer
│   ├── Entities/                   # Domain entities
│   │   ├── Product.cs
│   │   ├── Sale.cs
│   │   ├── Employee.cs
│   │   └── Customer.cs
│   └── Interfaces/                 # Service contracts
│       ├── Services/
│       │   └── IPrinterService.cs
│       └── Repositories/
│
├── CB.POS.Infrastructure/          # Infrastructure Layer
│   ├── Data/                       # Database
│   │   ├── PosDbContext.cs
│   │   └── DbInitializer.cs
│   ├── Hardware/                   # Hardware implementations
│   │   ├── Printers/
│   │   └── Scanners/
│   └── Services/                   # Service implementations
│
├── CB.POS.UI/                      # Presentation Layer
│   ├── Views/                      # XAML views
│   │   └── LoginView.xaml
│   ├── ViewModels/                 # View models
│   │   └── LoginViewModel.cs
│   ├── Services/                   # UI services
│   │   └── KeyboardFocusService.cs
│   ├── Strings/                    # Localization resources
│   │   ├── en-US/
│   │   ├── si-LK/
│   │   └── ta-LK/
│   ├── App.xaml                    # Application entry point
│   ├── App.xaml.cs                 # DI configuration
│   └── app.manifest                # Windows manifest
│
├── Architecture.md                 # Architecture overview
├── technical_specs.md              # Technical specifications
├── input_strategy.md               # Keyboard/input design
├── ai_roadmap.md                   # Future AI features
└── README.md                       # This file
```

---

## ⌨️ Keyboard Shortcuts

CB POS is designed for **keyboard-first operation**. All actions are accessible via hotkeys:

| Key | Action | Description |
|-----|--------|-------------|
| **F1** | Help | Shows keyboard shortcuts overlay |
| **F2** | Product Search | Search by name (for non-barcoded items) |
| **F3** | Change Quantity | Focus quantity field for selected item |
| **F4** | Void Line | Remove selected item from cart |
| **F5** | Checkout/Pay | Jump to payment screen |
| **F6** | Hold Bill | Suspend current transaction |
| **F7** | Recall Bill | Recall suspended transaction |
| **F8** | Price Check | Scan item to check price (no add to cart) |
| **F10** | Manager Menu | Returns/refunds/end of day (requires PIN) |
| **F12** | Logout/Lock | Security lock when leaving counter |
| **ESC** | Cancel/Back | Close modal or clear input |
| **Enter** | Add/Confirm | Add scanned item or confirm payment |
| **Space** | Quick Cash | (Payment screen) Auto-fill exact cash amount |

### Focus Management
The system uses an **aggressive focus strategy**:
- Cursor automatically returns to barcode input after every action
- Cashiers never need to click the text box to scan
- Implemented via `IFocusService` injected throughout the application

---

## 🌍 Localization

CB POS supports three languages with full Unicode rendering:

### Supported Languages
- **English (en-US)**: Default
- **Sinhala (si-LK)**: සිංහල
- **Tamil (ta-LK)**: தமிழ்

### Implementation
All UI strings use WinUI 3 resource system:
```xml
<!-- XAML -->
<TextBlock x:Uid="WelcomeMessage" />
```

Resource files:
- `Strings/en-US/Resources.resw`
- `Strings/si-LK/Resources.resw`
- `Strings/ta-LK/Resources.resw`

### Font Configuration
Global font family defined in `App.xaml`:
```xml
<Application.Resources>
    <FontFamily x:Key="AppFontFamily">Nirmala UI, Iskoola Pota</FontFamily>
</Application.Resources>
```

### Currency Formatting
```csharp
CultureInfo culture = new CultureInfo("si-LK");
string formatted = amount.ToString("C", culture); // Rs. 1,250.00
```

---

## 🖨️ Hardware Integration

### Thermal Printers
CB POS uses **raw ESC/POS commands** for industrial-grade printing:

```csharp
public interface IPrinterService
{
    Task PrintReceipt(Sale sale);
    Task OpenCashDrawer();
    Task<bool> TestConnection();
}
```

**Why not Windows Printing?**
- Faster (no print spooler)
- More reliable
- Direct control over formatting
- Cash drawer integration via RJ11

**Recommended Libraries**: `ESCPOS_NET` or raw socket streams

### Barcode Scanners
Supports two modes:
1. **HID Mode** (Modern USB scanners): Acts as keyboard
2. **Serial Mode** (Legacy scanners): `SerialPort` listener

**Scanner Discrimination Logic**:
- Input speed < 20ms per character = Scanner
- Input speed > 50ms per character = Human typing
- Routes scanner input to product search regardless of UI focus

### Cash Drawer
Triggered via printer using ESC/POS command:
```
ESC p m t1 t2 (0x1B 0x70 0x00 0x19 0xFA)
```

---

## 👨‍💻 Development Guidelines

### Coding Philosophy: "Industrial & Simple"

1. **Clean Architecture**: Strict separation of concerns
2. **SOLID Principles**: Every class has a single responsibility
3. **Dependency Injection**: Everything is injected, nothing is `new`'d
4. **Interface-Driven**: All services behind interfaces for testability

### Naming Conventions
```csharp
// ✅ Good
public class ProductService { }
private readonly IPrinterService _printerService;
public async Task CalculateTax() { }

// ❌ Bad
public class ProdSvc { }  // No abbreviations
private IPrinterService printerService;  // Missing underscore
public async Task CalcTax() { }  // Abbreviated
```

### Documentation Standards
```csharp
/// <summary>
/// Calculates the total tax for a sale transaction.
/// </summary>
/// <param name="sale">The sale to calculate tax for.</param>
/// <returns>The total tax amount in LKR.</returns>
public decimal CalculateTax(Sale sale)
{
    // Complex logic only gets inline comments
    var taxableAmount = sale.Subtotal - sale.Discounts;
    return taxableAmount * TAX_RATE;
}
```

### Error Handling
Global exception handling in `App.xaml.cs`:
```csharp
UnhandledException += App_UnhandledException;

private void App_UnhandledException(object sender, UnhandledExceptionEventArgs e)
{
    Log.Error(e.Exception, "Unhandled Exception");
    e.Handled = true;
    // Show user-friendly error dialog
}
```

### Logging
Serilog configured to write to:
```
%LOCALAPPDATA%\CB_POS\logs\log-YYYYMMDD.txt
```

Rolling daily logs with automatic cleanup.

---

## 🤖 AI Roadmap

Future AI-powered features planned:

### 1. Smart Inventory (Predictive)
Analyze sales history to suggest re-order levels:
> "Based on last month, you will run out of Keeris Samba Rice in 3 days"

### 2. Natural Language Reporting
Allow shop owners to query in Singlish/English:
> "Show me sales for last Friday" → Auto-converts to SQL/LINQ

### 3. Smart Search
Vector search for products:
> Searching "soap" shows "body wash" and "detergent" if exact match fails

### Implementation Hooks
Interfaces already defined for future AI integration:
```csharp
public interface IRecommendationEngine
{
    Task<IEnumerable<Product>> GetRecommendations(Sale currentSale);
}

public interface INaturalLanguageQuery
{
    Task<IEnumerable<Sale>> QuerySales(string naturalLanguageQuery);
}
```

---

## 🔧 Troubleshooting

### Build Issues

#### Error: "The name 'RollingInterval' does not exist"
**Solution**: Install Serilog packages
```bash
dotnet add package Serilog
dotnet add package Serilog.Extensions.Logging
dotnet add package Serilog.Sinks.File
```

#### Error: "Microsoft.Build.Packaging.Pri.Tasks.dll not found"
**Cause**: Visual Studio 2025 Preview uses v18.0 path, but WindowsAppSDK expects v17.0

**Solution**: Use Visual Studio's MSBuild instead of `dotnet build`
```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" `
  CB.POS.UI\CB.POS.UI.csproj /t:Build /p:Configuration=Debug
```

#### Database Not Created
**Solution**: Ensure `DbInitializer` is registered in DI:
```csharp
services.AddScoped<DbInitializer>();
```

### Runtime Issues

#### Sinhala/Tamil Text Not Rendering
**Solution**: Install required fonts:
- Iskoola Pota (Windows built-in)
- Nirmala UI (Windows built-in)

Verify font family in `App.xaml`:
```xml
<FontFamily x:Key="AppFontFamily">Nirmala UI, Iskoola Pota</FontFamily>
```

#### Barcode Scanner Not Working
**Checklist**:
1. Scanner in HID/Keyboard mode (not Serial)
2. Focus service returning focus to barcode input
3. Scanner configured with Enter suffix
4. Check scanner discrimination logic timing

---

## 📄 License

**Copyright © 2025 Ceybyte.com. All Rights Reserved.**

This software is proprietary and confidential. Unauthorized copying, distribution, modification, or use of this software, via any medium, is strictly prohibited without explicit written permission from Ceybyte.com.

### Restrictions
- ❌ No redistribution
- ❌ No modification without permission
- ❌ No commercial use without license
- ❌ No reverse engineering

For licensing inquiries, contact: [info@ceybyte.com](mailto:info@ceybyte.com)

---

## 🤝 Support

For technical support or inquiries:
- **Website**: [https://ceybyte.com](https://ceybyte.com)
- **Email**: support@ceybyte.com

---

<div align="center">

**Built with ❤️ in Sri Lanka**

*CB POS - Industrial-Grade Retail Solutions*

</div>
