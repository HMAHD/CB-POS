using Microsoft.UI.Xaml.Controls;
using System;

namespace CB.POS.UI.Services;

public interface INavigationService
{
    void Initialize(Frame shellFrame);
    void NavigateTo<TViewModel>() where TViewModel : class;
    void NavigateTo(Type viewModelType);
}

public class NavigationService : INavigationService
{
    private Frame? _shellFrame;

    public void Initialize(Frame shellFrame)
    {
        _shellFrame = shellFrame;
    }

    public void NavigateTo<TViewModel>() where TViewModel : class
    {
        NavigateTo(typeof(TViewModel));
    }

    public void NavigateTo(Type viewModelType)
    {
        if (_shellFrame == null)
        {
            return; // Or throw exception
        }

        // Convention: ViewModel name "XViewModel" maps to View name "XView"
        // This is a simple convention-based mapper.
        var viewName = viewModelType.FullName?.Replace("ViewModels", "Views").Replace("ViewModel", "View");
        if (viewName == null) return;

        var viewType = Type.GetType(viewName);
        if (viewType != null)
        {
            _shellFrame.Navigate(viewType);
        }
    }
}
