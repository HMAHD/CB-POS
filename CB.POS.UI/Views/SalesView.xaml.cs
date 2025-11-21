using CB.POS.UI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;

namespace CB.POS.UI.Views;

public sealed partial class SalesView : Page
{
    public SalesViewModel ViewModel { get; }

    public SalesView(SalesViewModel viewModel)
    {
        ViewModel = viewModel;
        this.InitializeComponent();
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        
        // Auto-focus barcode input when page loads
        BarcodeInput.Focus(FocusState.Keyboard);
    }

    private async void OnBarcodeKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == Windows.System.VirtualKey.Enter)
        {
            e.Handled = true;
            
            // Trigger the scan processing
            await ViewModel.ProcessScanCommand.ExecuteAsync(null);
            
            // Return focus to barcode input
            BarcodeInput.Focus(FocusState.Keyboard);
        }
    }

    // Keyboard Accelerator Handlers
    private void OnF1_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        BarcodeInput.Focus(FocusState.Keyboard);
    }

    private async void OnF2_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await ViewModel.SearchProductCommand.ExecuteAsync(null);
    }

    private async void OnF3_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await ViewModel.ChangeQuantityCommand.ExecuteAsync(null);
    }

    private void OnF4_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        ViewModel.VoidItemCommand.Execute(null);
    }

    private async void OnF5_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await ViewModel.PayCommand.ExecuteAsync(null);
    }
}
