using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CB.POS.Core.Interfaces.Services;
using CB.POS.UI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System;
using System.Threading.Tasks;

namespace CB.POS.UI.ViewModels;

public partial class ShellViewModel : ObservableObject
{
    private readonly ISessionContext _sessionContext;
    private readonly INavigationService _navigationService;
    private readonly DispatcherTimer _timer;

    [ObservableProperty]
    private string _currentUserName = "Guest";

    [ObservableProperty]
    private string _currentTime = "";

    public ShellViewModel(ISessionContext sessionContext, INavigationService navigationService)
    {
        _sessionContext = sessionContext;
        _navigationService = navigationService;

        if (_sessionContext.CurrentEmployee != null)
        {
            CurrentUserName = $"Cashier: {_sessionContext.CurrentEmployee.Name}";
        }

        // Initialize Clock
        _timer = new DispatcherTimer();
        _timer.Interval = TimeSpan.FromSeconds(1);
        _timer.Tick += (s, e) => CurrentTime = DateTime.Now.ToString("HH:mm:ss");
        _timer.Start();
        CurrentTime = DateTime.Now.ToString("HH:mm:ss"); // Initial set
    }

    [RelayCommand]
    private Task Logout()
    {
        _timer.Stop();
        _sessionContext.Logout();
        _navigationService.NavigateTo<LoginViewModel>();
        return Task.CompletedTask;
    }

    [RelayCommand]
    private async Task Navigate(NavigationViewSelectionChangedEventArgs args)
    {
        if (args.IsSettingsSelected)
        {
             var dialog = new ContentDialog
            {
                Title = "Feature Coming Soon",
                Content = "Settings module is under development.",
                CloseButtonText = "OK",
                XamlRoot = App.MainWindow.Content.XamlRoot
            };
            await dialog.ShowAsync();
            return;
        }

        var selectedItem = args.SelectedItem as NavigationViewItem;
        if (selectedItem?.Tag is string tag)
        {
            switch (tag)
            {
                case "SalesView":
                    // Navigate Frame inside ShellView? 
                    // Wait, NavigationService controls the RootFrame (Window content).
                    // We need a frame INSIDE ShellView for inner navigation.
                    // But for now, let's assume the requirement implies simple view switching or we need to expose the Shell's frame.
                    // Actually, the requirement says "Use a NavigationView as the root control". 
                    // Usually NavigationView handles its own Frame.
                    // Let's assume we need to handle the Frame navigation here.
                    // We'll expose a command that the View calls, and the View will have the Frame.
                    // OR, better: The View handles the event and calls the ViewModel, but the ViewModel decides what to do.
                    // Given the structure, let's keep it simple:
                    // The ShellView code-behind will handle the frame navigation based on this command, or we pass the Frame to the VM?
                    // No, let's use the NavigationService if it was designed for this.
                    // But NavigationService was initialized with RootFrame.
                    // We need a SECOND NavigationService or just manage the inner frame in CodeBehind/View for now as it's UI logic.
                    // However, the prompt asked for "Logic: Handle NavigationView.SelectionChanged".
                    
                    // Let's handle the "Coming Soon" here.
                    break;
                
                case "InventoryView":
                case "ReportsView":
                    var dialog = new ContentDialog
                    {
                        Title = "Feature Coming Soon",
                        Content = $"{tag.Replace("View", "")} module is under development.",
                        CloseButtonText = "OK",
                        XamlRoot = App.MainWindow.Content.XamlRoot
                    };
                    await dialog.ShowAsync();
                    break;
            }
        }
    }
}
