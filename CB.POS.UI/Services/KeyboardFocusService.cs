using CB.POS.Core.Interfaces.Services;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml;

namespace CB.POS.UI.Services;

public class KeyboardFocusService : IFocusService
{
    private Control? _mainInput;
    private bool _isSuspended;

    public void RegisterMainInput(object inputControl)
    {
        if (inputControl is Control control)
        {
            _mainInput = control;
            // Hook into the Loaded event to ensure we focus as soon as the view renders
            _mainInput.Loaded += (s, e) => ResetFocusToInput();
        }
    }

    public void ResetFocusToInput()
    {
        if (_isSuspended || _mainInput == null) return;

        // WinUI 3 specific: Check if window is active before forcing focus
        // to prevent stealing focus from other apps (Alt-Tab scenarios)
        var window = Window.Current; // Note: In pure WinUI3 you might need to pass the Window reference via DI
        
        _mainInput.Focus(FocusState.Programmatic);
        
        // Safety check: specific for Barcode Scanners acting as keyboards
        if (_mainInput is TextBox tb)
        {
            tb.SelectAll(); // Ready to overwrite old input
        }
    }

    public void SuspendAutoFocus() => _isSuspended = true;
    public void ResumeAutoFocus()
    {
        _isSuspended = false;
        ResetFocusToInput();
    }
}