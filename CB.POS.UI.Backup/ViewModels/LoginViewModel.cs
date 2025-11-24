using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CB.POS.Infrastructure.Data;
using CB.POS.Core.Interfaces.Services;
using Microsoft.EntityFrameworkCore;
using System.Threading.Tasks;
using System.Linq;
using Microsoft.UI.Xaml.Controls;
using CB.POS.UI.Services;
using Serilog;

namespace CB.POS.UI.ViewModels;

public partial class LoginViewModel : ObservableObject
{
    private readonly PosDbContext _context;
    private readonly IFocusService _focusService;
    private readonly ISessionContext _sessionContext;
    private readonly INavigationService _navigationService;

    [ObservableProperty]
    private string _pinInput = "";

    [ObservableProperty]
    private string _errorMessage = "";

    /// <summary>
    /// Masked PIN display (shows dots instead of actual digits).
    /// </summary>
    public string MaskedPin => new string('●', PinInput.Length);

    public LoginViewModel(PosDbContext context, IFocusService focusService, ISessionContext sessionContext, INavigationService navigationService)
    {
        _context = context;
        _focusService = focusService;
        _sessionContext = sessionContext;
        _navigationService = navigationService;
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
        try
        {
            Log.Information("LoginAsync called. PIN: {PinLength}", PinInput?.Length ?? 0);
            if (string.IsNullOrWhiteSpace(PinInput))
            {
                Log.Warning("Login failed: PIN is empty.");
                ErrorMessage = "Please enter a PIN.";
                return;
            }

            Log.Information("Querying database for employee...");
            var employee = await _context.Employees
                .FirstOrDefaultAsync(e => e.PinHash == PinInput && e.IsActive);

            if (employee != null)
            {
                Log.Information("Employee found: {EmployeeName}. Authenticating...", employee.Name);
                ErrorMessage = "";
                PinInput = ""; // Clear for security
                OnPropertyChanged(nameof(MaskedPin));
                
                // Set Authentication
                _sessionContext.SetAuthentication(employee);
                Log.Information("Authentication set.");
                
                // Navigate to Shell
                Log.Information("Navigating to ShellViewModel...");
                _navigationService.NavigateTo<ShellViewModel>();
                Log.Information("Navigation call complete.");
            }
            else
            {
                Log.Warning("Login failed: Invalid PIN.");
                ErrorMessage = "Invalid PIN. Please try again.";
                PinInput = "";
                OnPropertyChanged(nameof(MaskedPin));
                
                // Return focus to PIN input
                _focusService.ResetFocusToInput();
            }
        }
        catch (System.Exception ex)
        {
            Log.Error(ex, "Error during login execution.");
            ErrorMessage = "An error occurred. Please check logs.";
        }
    }
}
