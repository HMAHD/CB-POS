using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Windows.System;

namespace CB.POS.UI.Views;

public sealed partial class ShellView : Page
{
    public ShellViewModel? ViewModel { get; }

    public ShellView()
    {
        this.InitializeComponent();
        ViewModel = ((App)App.Current).Host.Services.GetService<ShellViewModel>();
        this.DataContext = ViewModel;
        
        // Keyboard Accelerators
        var logoutAccelerator = new KeyboardAccelerator { Key = VirtualKey.F12 };
        logoutAccelerator.Invoked += (s, e) => ViewModel?.LogoutCommand.Execute(null);
        this.KeyboardAccelerators.Add(logoutAccelerator);

        var salesAccelerator = new KeyboardAccelerator { Key = VirtualKey.F1 };
        salesAccelerator.Invoked += (s, e) => 
        {
            if (NavView?.MenuItems?.Count > 0)
            {
                NavView.SelectedItem = NavView.MenuItems[0]; // Select Sales
            }
        };
        this.KeyboardAccelerators.Add(salesAccelerator);
    }

    private void NavView_Loaded(object sender, RoutedEventArgs e)
    {
        // Set initial selection
        if (NavView?.MenuItems?.Count > 0)
        {
            NavView.SelectedItem = NavView.MenuItems[0];
        }
    }

    private void NavView_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        // Delegate logic to ViewModel first (for "Coming Soon" checks)
        ViewModel?.NavigateCommand.Execute(args);

        // Handle Frame Navigation if valid
        if (args.IsSettingsSelected)
        {
            // Settings handling handled by VM for now (Coming Soon)
        }
        else if (args.SelectedItem is NavigationViewItem item && item.Tag is string tag)
        {
            if (tag == "SalesView")
            {
                ContentFrame.Navigate(typeof(SalesView));
            }
            // Other views are handled by VM dialogs for now
        }
    }

    private void Page_Loaded(object sender, RoutedEventArgs e)
    {
        // Ensure focus is somewhere useful if needed
    }
}
