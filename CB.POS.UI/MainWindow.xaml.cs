using Microsoft.UI.Xaml;

namespace CB.POS.UI;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        this.InitializeComponent();
        Title = "CB POS";
        
        // Navigate to Login View
        AppFrame.Navigate(typeof(Views.LoginView));
    }
}
