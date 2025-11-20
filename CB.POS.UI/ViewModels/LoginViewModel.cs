using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CB.POS.Infrastructure.Data;
using CB.POS.Core.Interfaces.Services;
using Microsoft.EntityFrameworkCore;
using System.Threading.Tasks;
using System.Linq;
using Microsoft.UI.Xaml.Controls;

namespace CB.POS.UI.ViewModels;

public partial class LoginViewModel : ObservableObject
{
    private readonly PosDbContext _context;
    private readonly IFocusService _focusService;

    [ObservableProperty]
    private string _pinInput = "";

    [ObservableProperty]
    private string _errorMessage = "";

    /// <summary>
    /// Masked PIN display (shows dots instead of actual digits).
    /// </summary>
    public string MaskedPin => new string('●', PinInput.Length);

    public LoginViewModel(PosDbContext context, IFocusService focusService)
    {
        _context = context;
        _focusService = focusService;
    }

    [RelayCommand]
    private void AppendNumber(string number)
    {
        ErrorMessage = ""; // Clear error on new input
        if (PinInput.Length < 6) // Limit PIN length
        {
            PinInput += number;
            OnPropertyChanged(nameof(MaskedPin));
        }
    }

    [RelayCommand]
    private void Backspace()
    {
        ErrorMessage = "";
        if (!string.IsNullOrEmpty(PinInput))
        {
            PinInput = PinInput.Substring(0, PinInput.Length - 1);
            OnPropertyChanged(nameof(MaskedPin));
        }
    }

    [RelayCommand]
    private async Task LoginAsync()
    {
        if (string.IsNullOrWhiteSpace(PinInput))
        {
            ErrorMessage = "Please enter a PIN.";
            return;
        }

        // In a real app, hash the input before comparing.
        // For MVP, we are comparing against the "PinHash" directly as per the seed data "1234".
        // Ideally: var hash = HashService.Hash(PinInput);
        
        var employee = await _context.Employees
            .FirstOrDefaultAsync(e => e.PinHash == PinInput && e.IsActive);

        if (employee != null)
        {
            ErrorMessage = "";
            PinInput = ""; // Clear for security
            OnPropertyChanged(nameof(MaskedPin));
            
            // Navigate to Shell (Placeholder)
            var dialog = new ContentDialog
            {
                Title = "Login Successful",
                Content = $"Welcome, {employee.Name}!",
                CloseButtonText = "OK",
                XamlRoot = App.MainWindow.Content.XamlRoot
            };
            await dialog.ShowAsync();
            
            // TODO: Actual Navigation to ShellView
        }
        else
        {
            ErrorMessage = "Invalid PIN. Please try again.";
            PinInput = "";
            OnPropertyChanged(nameof(MaskedPin));
            
            // Return focus to PIN input
            _focusService.ResetFocusToInput();
        }
    }
}
