using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Windowing;
using Windows.Graphics;
using System.Runtime.InteropServices;
using WinRT;

namespace CB.POS.UI;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        this.InitializeComponent();
        Title = "CB POS";

        // Maximize window on startup
        MaximizeWindow();

        var navService = ((App)App.Current).Host.Services.GetService(typeof(Services.INavigationService)) as Services.INavigationService;
        navService?.Initialize(RootFrame);
        
        // Navigate to Login View
        navService?.NavigateTo<ViewModels.LoginViewModel>();
    }

    private void MaximizeWindow()
    {
        var hWnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
        var windowId = Microsoft.UI.Win32Interop.GetWindowIdFromWindow(hWnd);
        var appWindow = AppWindow.GetFromWindowId(windowId);
        
        if (appWindow != null)
        {
            var displayArea = DisplayArea.GetFromWindowId(windowId, DisplayAreaFallback.Primary);
            if (displayArea != null)
            {
                var workArea = displayArea.WorkArea;
                appWindow.MoveAndResize(new RectInt32(
                    workArea.X,
                    workArea.Y,
                    workArea.Width,
                    workArea.Height
                ));
            }
        }
    }
}
