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

                // 4. Views & ViewModels
                services.AddTransient<MainWindow>();
                services.AddTransient<LoginViewModel>();
                services.AddTransient<LoginView>();
                
                // Future: Register other ViewModels and Views here
                // services.AddTransient<MainViewModel>();
            })
            .Build();

        UnhandledException += App_UnhandledException;
    }

    private void App_UnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        // Log the exception
        Log.Error(e.Exception, "Unhandled Exception");

        // Prevent crash if possible
        e.Handled = true;

        // Try to show a dialog (only if we have a window)
        if (MainWindow != null && MainWindow.Content is FrameworkElement fe && fe.XamlRoot != null)
        {
            // We can't await in this synchronous event handler easily without blocking, 
            // but for a critical error we might just log and swallow or try to invoke on dispatcher.
            // For now, we just log and mark handled.
        }
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        var host = this.Host; // Access your built host
        using (var scope = host.Services.CreateScope())
        {
            var initializer = scope.ServiceProvider.GetRequiredService<DbInitializer>();
            initializer.Initialize();
        }
        await Host.StartAsync();

        // Resolve MainWindow from DI
        MainWindow = Host.Services.GetRequiredService<MainWindow>();
        MainWindow.Activate();
    }
}
