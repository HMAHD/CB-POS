using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Data;
using System;

namespace CB.POS.UI.Converters;

/// <summary>
/// Converts empty or null string to Collapsed visibility, otherwise Visible.
/// Used to hide error message containers when no error message is present.
/// </summary>
public class EmptyStringToCollapsedConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, string language)
    {
        return string.IsNullOrWhiteSpace(value as string) ? Visibility.Collapsed : Visibility.Visible;
    }

    public object ConvertBack(object value, Type targetType, object parameter, string language)
    {
        throw new NotImplementedException();
    }
}
