using Microsoft.UI.Xaml;

namespace CB.POS.UI;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        this.InitializeComponent();
        Title = "CB POS";

        var navService = ((App)App.Current).Host.Services.GetService(typeof(Services.INavigationService)) as Services.INavigationService;
        navService?.Initialize(RootFrame);
        
        // Navigate to Login View
        navService?.NavigateTo<ViewModels.LoginViewModel>();
    }
}
