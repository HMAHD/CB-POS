using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;

namespace CB.POS.UI.Views;

public sealed partial class SalesView : Page
{
    public SalesViewModel ViewModel { get; }

    public SalesView()
    {
        this.InitializeComponent();
        // Fallback or default resolution if needed, though usually we expect it via navigation or DI
        // For now, let's resolve it from DI to be safe, or wait for OnNavigatedTo
        ViewModel = ((App)App.Current).Host.Services.GetRequiredService<SalesViewModel>();
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        
        // If ViewModel was passed as parameter, use it (though we already resolved from DI)
        // In this architecture, singleton/scoped ViewModels from DI are preferred.
        // if (e.Parameter is SalesViewModel vm)
        // {
        //    ViewModel = vm;
        // }
        
        // Auto-focus barcode input when page loads
        // BarcodeInput.Focus(FocusState.Keyboard);
    }

    private void OnBarcodeKeyDown(object sender, KeyRoutedEventArgs e)
    {
        /*
        if (e.Key == Windows.System.VirtualKey.Enter)
        {
            e.Handled = true;
            
            // Trigger the scan processing
            await ViewModel.ProcessScanCommand.ExecuteAsync(null);
            
            // Return focus to barcode input
            BarcodeInput.Focus(FocusState.Keyboard);
        }
        */
    }

    // Keyboard Accelerator Handlers
    private void OnF1_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        /*
        args.Handled = true;
        BarcodeInput.Focus(FocusState.Keyboard);
        */
    }

    private void OnF2_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        /*
        args.Handled = true;
        await ViewModel.SearchProductCommand.ExecuteAsync(null);
        */
    }

    private void OnF3_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        /*
        args.Handled = true;
        await ViewModel.ChangeQuantityCommand.ExecuteAsync(null);
        */
    }

    private void OnF4_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        /*
        args.Handled = true;
        ViewModel.VoidItemCommand.Execute(null);
        */
    }

    private void OnF5_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        /*
        args.Handled = true;
        await ViewModel.PayCommand.ExecuteAsync(null);
        */
    }
}
