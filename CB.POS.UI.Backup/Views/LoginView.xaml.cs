using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml;
using Windows.System;

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

            VirtualKey.Number7 or VirtualKey.NumberPad7 => "7",
            VirtualKey.Number8 or VirtualKey.NumberPad8 => "8",
            VirtualKey.Number9 or VirtualKey.NumberPad9 => "9",
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
