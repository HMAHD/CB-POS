using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml.Controls;

namespace CB.POS.UI.Views;

public sealed partial class LoginView : Page
{
    public LoginViewModel ViewModel { get; }

    public LoginView()
    {
        this.InitializeComponent();
        
        // Resolve ViewModel from the App's Host
        ViewModel = ((App)App.Current).Host.Services.GetRequiredService<LoginViewModel>();
    }
}
