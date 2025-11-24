using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Data;
using System;

namespace CB.POS.UI.Converters
{
    public class EmptyStringToVisibilityConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, string language)
        {
            string? input = value as string;
            return string.IsNullOrWhiteSpace(input) ? Visibility.Collapsed : Visibility.Visible;
        }

        public object ConvertBack(object value, Type targetType, object parameter, string language)
        {
            throw new NotImplementedException();
        }
    }
}
