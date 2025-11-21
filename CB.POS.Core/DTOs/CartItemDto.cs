using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace CB.POS.Core.DTOs;

/// <summary>
/// Data transfer object for cart items displayed in the UI.
/// Implements INotifyPropertyChanged for two-way binding support.
/// </summary>
public class CartItemDto : INotifyPropertyChanged
{
    private string _barcode = string.Empty;
    private string _productName = string.Empty;
    private decimal _quantity;
    private decimal _unitPrice;
    private decimal _lineTotal;
    private bool _isWeighted;

    public string Barcode
    {
        get => _barcode;
        set
        {
            if (_barcode != value)
            {
                _barcode = value;
                OnPropertyChanged();
            }
        }
    }

    public string ProductName
    {
        get => _productName;
        set
        {
            if (_productName != value)
            {
                _productName = value;
                OnPropertyChanged();
            }
        }
    }

    public decimal Quantity
    {
        get => _quantity;
        set
        {
            if (_quantity != value)
            {
                _quantity = value;
                OnPropertyChanged();
                // Auto-recalculate line total when quantity changes
                LineTotal = _quantity * _unitPrice;
            }
        }
    }

    public decimal UnitPrice
    {
        get => _unitPrice;
        set
        {
            if (_unitPrice != value)
            {
                _unitPrice = value;
                OnPropertyChanged();
                // Auto-recalculate line total when price changes
                LineTotal = _quantity * _unitPrice;
            }
        }
    }

    public decimal LineTotal
    {
        get => _lineTotal;
        set
        {
            if (_lineTotal != value)
            {
                _lineTotal = value;
                OnPropertyChanged();
            }
        }
    }

    public bool IsWeighted
    {
        get => _isWeighted;
        set
        {
            if (_isWeighted != value)
            {
                _isWeighted = value;
                OnPropertyChanged();
            }
        }
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    protected virtual void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
