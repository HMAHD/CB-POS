using System;
using System.IO;
using System.Runtime.ExceptionServices;
using CB.POS.Core.Interfaces.Services;
using CB.POS.Infrastructure.Data;
using CB.POS.UI.Services;
using CB.POS.UI.ViewModels;
using CB.POS.UI.Views;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Serilog;
using Serilog.Debugging;
using Microsoft.EntityFrameworkCore;

namespace CB.POS.UI;

public partial class App : Application
{
    public IHost Host { get; }
    public static Window MainWindow { get; private set; } = null!;

    public App()
    {
        InitializeComponent();

        // Early: capture first-chance exceptions to catch pre-handshake failures
        AppDomain.CurrentDomain.FirstChanceException += (_, e) =>
        {
            System.Diagnostics.Debug.WriteLine($"FirstChance: {e.Exception.GetType()}: {e.Exception.Message}");
        };

        // 1. Logging (Serilog) directory prep
        var logPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "CB_POS", "logs", "log-.txt");

        try
        {
            var logDir = Path.GetDirectoryName(logPath);
            if (!string.IsNullOrWhiteSpace(logDir))
                Directory.CreateDirectory(logDir);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Failed to create log directory: {ex.Message}");
        }

        // Enable Serilog internal self-log to Debug output (helps if sink assembly missing)
        SelfLog.Enable(msg => System.Diagnostics.Debug.WriteLine("Serilog SelfLog: " + msg));

        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Debug()
            .WriteTo.File(logPath, rollingInterval: RollingInterval.Day, shared: true)
            .CreateLogger();

        // 2. Generic Host
        Host = Microsoft.Extensions.Hosting.Host.CreateDefaultBuilder()
            .UseSerilog() // Ensure host itself uses Serilog pipeline
            .ConfigureServices((context, services) =>
            {
                // Database (explicit provider configuration)
                var dbFile = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "CB_POS",
                    "cbpos.db");

                services.AddDbContext<PosDbContext>(options =>
                {
                    options.UseSqlite($"Data Source={dbFile}");
                });
                services.AddScoped<DbInitializer>();

                // Services
                services.AddSingleton<IFocusService, KeyboardFocusService>();
                services.AddSingleton<ISessionContext, SessionContext>();
                services.AddSingleton<INavigationService, NavigationService>();
                services.AddSingleton<ICartService, CartService>();

                // Views & ViewModels
                services.AddTransient<MainWindow>();
                services.AddTransient<LoginViewModel>();
                services.AddTransient<LoginView>();
                services.AddTransient<ShellViewModel>();
                services.AddTransient<ShellView>();
                services.AddTransient<SalesViewModel>();
                services.AddTransient<SalesView>();
            })
            .Build();

        UnhandledException += App_UnhandledException;
    }

    private void App_UnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        Log.Error(e.Exception, "Unhandled Exception");
        e.Handled = true;
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        try
        {
            // Start host first (HostedServices may depend on DI)
            await Host.StartAsync();

            // DB initialization in controlled scope
            using (var scope = Host.Services.CreateScope())
            {
                var initializer = scope.ServiceProvider.GetRequiredService<DbInitializer>();
                try
                {
                    initializer.Initialize();
                }
                catch (Exception ex)
                {
                    Log.Fatal(ex, "Database initialization failed");
                    // You could show a dialog or fallback here; abort to prevent partial state.
                    Environment.FailFast("Critical failure initializing database.", ex);
                }
            }

            MainWindow = Host.Services.GetRequiredService<MainWindow>();
            MainWindow.Activate();
        }
        catch (Exception ex)
        {
            Log.Fatal(ex, "Fatal startup exception");
            Environment.FailFast("Startup aborted.", ex);
        }
    }
}
