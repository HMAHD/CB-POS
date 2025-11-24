using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace CB.POS.UI.Views;

public sealed partial class ShellView : Page
{
    public ShellViewModel ViewModel { get; }

    public string CurrentUserName => ViewModel.CurrentUserName;

    public ShellView()
    {
        this.InitializeComponent();
        ViewModel = ((App)App.Current).Host.Services.GetRequiredService<ShellViewModel>();
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        // Navigate to SalesView by default
        // NavView.SelectedItem = NavView.MenuItems[0];
    }

    private void NavView_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        /*
        if (args.IsSettingsSelected)
        {
            // Settings handling handled by VM for now (Coming Soon)
        }
        else if (args.SelectedItem is NavigationViewItem item && item.Tag is string tag)
        {
            if (tag == "Sales")
            {
                NavView.Header = "Sales";
                ContentFrame.Navigate(typeof(SalesView));
            }
            else if (tag == "Inventory")
            {
                NavView.Header = "Inventory";
                // Navigate to Inventory View
            }
            else if (tag == "Reports")
            {
                NavView.Header = "Reports";
                // Navigate to Reports View
            }
        }
        */
    }

    private void ThemeToggle_Toggled(object sender, RoutedEventArgs e)
    {
        /*
        if (sender is ToggleSwitch toggleSwitch)
        {
            if (this.XamlRoot != null && this.XamlRoot.Content is FrameworkElement rootElement)
            {
                rootElement.RequestedTheme = toggleSwitch.IsOn ? ElementTheme.Light : ElementTheme.Dark;
            }
        }
        */
    }
}
