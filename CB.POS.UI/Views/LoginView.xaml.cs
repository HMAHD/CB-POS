using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

namespace CB.POS.UI.Views;

public sealed partial class LoginView : Page
{
    public LoginViewModel? ViewModel { get; }

    public LoginView()
    {
        this.InitializeComponent();
        
        // Resolve ViewModel from the App's Host
        ViewModel = ((App)App.Current).Host.Services.GetRequiredService<LoginViewModel>();
    }

    /// <summary>
    /// Handles number key presses (0-9) from both regular and numpad keys.
    /// </summary>
    private void OnNumberKey_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        // Extract the digit from the key
        var key = args.KeyboardAccelerator.Key;
        string? digit = key switch
        {
            Windows.System.VirtualKey.Number0 or Windows.System.VirtualKey.NumberPad0 => "0",
            Windows.System.VirtualKey.Number1 or Windows.System.VirtualKey.NumberPad1 => "1",
            Windows.System.VirtualKey.Number2 or Windows.System.VirtualKey.NumberPad2 => "2",
            Windows.System.VirtualKey.Number3 or Windows.System.VirtualKey.NumberPad3 => "3",
            Windows.System.VirtualKey.Number4 or Windows.System.VirtualKey.NumberPad4 => "4",
            Windows.System.VirtualKey.Number5 or Windows.System.VirtualKey.NumberPad5 => "5",
            Windows.System.VirtualKey.Number6 or Windows.System.VirtualKey.NumberPad6 => "6",
            Windows.System.VirtualKey.Number7 or Windows.System.VirtualKey.NumberPad7 => "7",
            Windows.System.VirtualKey.Number8 or Windows.System.VirtualKey.NumberPad8 => "8",
            Windows.System.VirtualKey.Number9 or Windows.System.VirtualKey.NumberPad9 => "9",
            _ => null
        };

        if (digit != null)
        {
            ViewModel?.AppendNumberCommand.Execute(digit);
            args.Handled = true;
        }
    }

    /// <summary>
    /// Handles backspace key press.
    /// </summary>
    private void OnBackspace_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        ViewModel?.BackspaceCommand.Execute(null);
        args.Handled = true;
    }

    /// <summary>
    /// Handles enter key press to submit the PIN.
    /// </summary>
    private void OnEnter_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        ViewModel?.LoginCommand.Execute(null);
        args.Handled = true;
    }
}
