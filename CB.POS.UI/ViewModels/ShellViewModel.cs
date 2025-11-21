using CommunityToolkit.Mvvm.ComponentModel;
using CB.POS.Core.Interfaces.Services;

namespace CB.POS.UI.ViewModels;

public partial class ShellViewModel : ObservableObject
{
    private readonly ISessionContext _sessionContext;

    [ObservableProperty]
    private string _welcomeMessage = "Welcome to CB POS Shell";

    public ShellViewModel(ISessionContext sessionContext)
    {
        _sessionContext = sessionContext;
        if (_sessionContext.CurrentEmployee != null)
        {
            WelcomeMessage = $"Welcome, {_sessionContext.CurrentEmployee.Name}!";
        }
    }
}
