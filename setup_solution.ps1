$dotnet = "C:\Program Files\dotnet\dotnet.exe"

# 1. Install WinUI 3 Templates
Write-Host "Installing WinUI 3 Templates..."
& $dotnet new install Microsoft.WindowsAppSDK.Templates

# 2. Create Solution
Write-Host "Creating Solution..."
& $dotnet new sln -n CB-POS

# 3. Create Projects
Write-Host "Creating Projects..."
New-Item -ItemType Directory -Force -Path src

# Domain
& $dotnet new classlib -n CB_POS.Domain -o src/CB_POS.Domain -f net10.0

# Application
& $dotnet new classlib -n CB_POS.Application -o src/CB_POS.Application -f net10.0
& $dotnet add src/CB_POS.Application/CB_POS.Application.csproj reference src/CB_POS.Domain/CB_POS.Domain.csproj

# Infrastructure
& $dotnet new classlib -n CB_POS.Infrastructure -o src/CB_POS.Infrastructure -f net10.0
& $dotnet add src/CB_POS.Infrastructure/CB_POS.Infrastructure.csproj reference src/CB_POS.Application/CB_POS.Application.csproj
& $dotnet add src/CB_POS.Infrastructure/CB_POS.Infrastructure.csproj reference src/CB_POS.Domain/CB_POS.Domain.csproj

# Presentation (WinUI 3)
& $dotnet new winui -n CB_POS.Presentation -o src/CB_POS.Presentation
& $dotnet add src/CB_POS.Presentation/CB_POS.Presentation.csproj reference src/CB_POS.Application/CB_POS.Application.csproj
& $dotnet add src/CB_POS.Presentation/CB_POS.Presentation.csproj reference src/CB_POS.Infrastructure/CB_POS.Infrastructure.csproj

# 4. Add to Solution
Write-Host "Adding projects to solution..."
& $dotnet sln CB-POS.sln add src/CB_POS.Domain/CB_POS.Domain.csproj
& $dotnet sln CB-POS.sln add src/CB_POS.Application/CB_POS.Application.csproj
& $dotnet sln CB-POS.sln add src/CB_POS.Infrastructure/CB_POS.Infrastructure.csproj
& $dotnet sln CB-POS.sln add src/CB_POS.Presentation/CB_POS.Presentation.csproj

Write-Host "Setup Complete!"
