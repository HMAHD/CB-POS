using Microsoft.UI.Xaml.Controls;
using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;

namespace CB.POS.UI.Views;

public sealed partial class ShellView : Page
{
    public ShellViewModel ViewModel { get; }

    public ShellView()
    {
        this.InitializeComponent();
        ViewModel = App.Current.Services.GetService<ShellViewModel>();
    }
}
