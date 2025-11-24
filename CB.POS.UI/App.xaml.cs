using System;
using System.IO;
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

namespace CB.POS.UI;

public partial class App : Application
{
    public IHost Host { get; }

    public static Window MainWindow { get; private set; } = null!;

    public App()
    {
        this.InitializeComponent();

        Host = Microsoft.Extensions.Hosting.Host.CreateDefaultBuilder()
            .ConfigureServices((context, services) =>
            {
                // 1. Logging (Serilog)
                var logPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CB_POS", "logs", "log-.txt");
                Log.Logger = new LoggerConfiguration()
                    .WriteTo.File(logPath, rollingInterval: RollingInterval.Day)
                    .CreateLogger();
                
                services.AddLogging(loggingBuilder => loggingBuilder.AddSerilog(dispose: true));

                // 2. Database
                services.AddDbContext<PosDbContext>();
                services.AddScoped<DbInitializer>();

                // 3. Services
                services.AddSingleton<IFocusService, KeyboardFocusService>();
                services.AddSingleton<ISessionContext, SessionContext>();
                services.AddSingleton<INavigationService, NavigationService>();
                services.AddSingleton<ICartService, CartService>();

                // 4. Views & ViewModels
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
        var host = this.Host;
        using (var scope = host.Services.CreateScope())
        {
            var initializer = scope.ServiceProvider.GetRequiredService<DbInitializer>();
            initializer.Initialize();
        }
        await Host.StartAsync();

        MainWindow = Host.Services.GetRequiredService<MainWindow>();
        MainWindow.Activate();
    }
}
