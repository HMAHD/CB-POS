using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

namespace CB.POS.UI.Views;

public sealed partial class ShellView : Page
{
    public ShellViewModel ViewModel { get; }

    public string CurrentUserName => ViewModel.CurrentUserName;

    public ShellView()
    {
        this.InitializeComponent();
        ViewModel = ((App)App.Current).Host.Services.GetRequiredService<ShellViewModel>();
        
        // Ensure NavView is loaded before selecting item
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        // Select Sales by default
        NavView.SelectedItem = NavView.MenuItems[0];
    }

    private void NavView_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is NavigationViewItem item)
        {
            string tag = item.Tag?.ToString() ?? "";
            
            switch (tag)
            {
                case "SalesView":
                    ContentFrame.Navigate(typeof(SalesView), ((App)App.Current).Host.Services.GetRequiredService<SalesViewModel>());
                    break;
                case "InventoryView":
                case "ReportsView":
                case "SettingsView":
                    // Use ViewModel command to show "Coming Soon" dialog
                    ViewModel.NavigateCommand.Execute(args);
                    // Revert selection if needed, or just show empty/placeholder
                    break;
            }
        }
    }

    private void Logout_Tapped(object sender, TappedRoutedEventArgs e)
    {
        ViewModel.LogoutCommand.Execute(null);
    }
}
