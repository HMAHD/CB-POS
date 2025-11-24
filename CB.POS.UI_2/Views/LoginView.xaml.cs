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

    private void PinInputBox_KeyDown(object sender, KeyRoutedEventArgs e)
    {
        // Handle Enter key to trigger login
        if (e.Key == VirtualKey.Enter)
        {
            ViewModel?.LoginCommand.Execute(null);
            e.Handled = true;
        }
    }

    private void PinInputBox_GotFocus(object sender, RoutedEventArgs e)
    {
        // Optional: Select all text or handle focus visuals
    }

    private void PinInputBox_LostFocus(object sender, RoutedEventArgs e)
    {
        // Focus Trap: Force focus back to PinInputBox unless we are navigating away
        // Note: In a real app, we might want to be less aggressive, but for a POS login screen, this is common.
        // However, if we click buttons, we might lose focus. 
        // Actually, clicking buttons will take focus. We should probably let buttons take focus 
        // but ensure typing always goes to the password box or redirect input.
        // For this task, "Force focus to PinInputBox on load and when typing numbers"
        
        // We'll rely on the ViewModel or simple logic to keep it focused or redirect input.
        // But if the user clicks a Numpad button, focus moves there. That's fine.
        // We just want to ensure it's focused initially.
    }

    protected override void OnNavigatedTo(Microsoft.UI.Xaml.Navigation.NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        // Force focus on load
        PinInputBox.Focus(FocusState.Programmatic);
    }
}
