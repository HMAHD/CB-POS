using CB.POS.UI.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;
using Windows.System;

namespace CB.POS.UI.Views;

public sealed partial class LoginView : Page
{
    public LoginViewModel ViewModel { get; }

    public LoginView()
    {
        this.InitializeComponent();
        ViewModel = ((App)Application.Current).Host.Services.GetRequiredService<LoginViewModel>();
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        // Focus the hidden input box to capture keyboard input immediately
        PinInputBox.Focus(FocusState.Programmatic);
    }

    private void PinInputBox_KeyDown(object sender, KeyRoutedEventArgs e)
    {
        // Handle Enter key
        if (e.Key == VirtualKey.Enter)
        {
            if (ViewModel.LoginCommand.CanExecute(null))
            {
                ViewModel.LoginCommand.Execute(null);
            }
            e.Handled = true;
            return;
        }
        
        // Handle Backspace
        if (e.Key == VirtualKey.Back)
        {
             ViewModel.BackspaceCommand.Execute(null);
             e.Handled = true;
             return;
        }

        // Handle numeric keys
        string? digit = e.Key switch
        {
            VirtualKey.Number0 or VirtualKey.NumberPad0 => "0",
            VirtualKey.Number1 or VirtualKey.NumberPad1 => "1",
            VirtualKey.Number2 or VirtualKey.NumberPad2 => "2",
            VirtualKey.Number3 or VirtualKey.NumberPad3 => "3",
            VirtualKey.Number4 or VirtualKey.NumberPad4 => "4",
            VirtualKey.Number5 or VirtualKey.NumberPad5 => "5",
            VirtualKey.Number6 or VirtualKey.NumberPad6 => "6",
            VirtualKey.Number7 or VirtualKey.NumberPad7 => "7",
            VirtualKey.Number8 or VirtualKey.NumberPad8 => "8",
            VirtualKey.Number9 or VirtualKey.NumberPad9 => "9",
            _ => null
        };

        if (digit != null)
        {
            ViewModel.AppendNumberCommand.Execute(digit);
            e.Handled = true;
        }
    }
}
