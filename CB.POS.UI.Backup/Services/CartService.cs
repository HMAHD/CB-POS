using CB.POS.Core.DTOs;
using CB.POS.Core.Entities;
using CB.POS.Core.Interfaces.Services;
using System.Collections.ObjectModel;

namespace CB.POS.UI.Services;

/// <summary>
/// In-memory cart management service - the "brain" of the POS screen.
/// Manages the current sale and provides automatic calculation of totals.
/// </summary>
public class CartService : ICartService
{
    private decimal _totalAmount;
    private int _itemCount;

    public CartService()
    {
        CartItems = new ObservableCollection<CartItemDto>();
        
        // Subscribe to collection changes to auto-update totals
        CartItems.CollectionChanged += (s, e) => RecalculateTotals();
    }

    public ObservableCollection<CartItemDto> CartItems { get; }

    public decimal TotalAmount
    {
        get => _totalAmount;
        private set
        {
            _totalAmount = value;
            OnCartUpdated();
        }
    }

    public int ItemCount
    {
        get => _itemCount;
        private set
        {
            _itemCount = value;
            OnCartUpdated();
        }
    }

    public event EventHandler? CartUpdated;

    public void AddItem(Product product, decimal quantity = 1)
    {
        if (product == null)
            throw new ArgumentNullException(nameof(product));

        if (quantity <= 0)
            throw new ArgumentException("Quantity must be greater than zero.", nameof(quantity));

        // Check if item already exists in cart
        var existingItem = CartItems.FirstOrDefault(item => item.Barcode == product.Barcode);

        if (existingItem != null)
        {
            // Item exists - increase quantity
            existingItem.Quantity += quantity;
        }
        else
        {
            // New item - add to cart
            var cartItem = new CartItemDto
            {
                Barcode = product.Barcode,
                ProductName = product.Name,
                Quantity = quantity,
                UnitPrice = product.Price,
                IsWeighted = product.IsWeighted
            };
            // LineTotal is auto-calculated by CartItemDto when Quantity and UnitPrice are set

            CartItems.Add(cartItem);
        }

        RecalculateTotals();
    }

    public void RemoveItem(string barcode)
    {
        if (string.IsNullOrWhiteSpace(barcode))
            throw new ArgumentException("Barcode cannot be empty.", nameof(barcode));

        var item = CartItems.FirstOrDefault(i => i.Barcode == barcode);
        if (item != null)
        {
            CartItems.Remove(item);
            RecalculateTotals();
        }
    }

    public void UpdateQuantity(string barcode, decimal newQuantity)
    {
        if (string.IsNullOrWhiteSpace(barcode))
            throw new ArgumentException("Barcode cannot be empty.", nameof(barcode));

        if (newQuantity <= 0)
            throw new ArgumentException("Quantity must be greater than zero.", nameof(newQuantity));

        var item = CartItems.FirstOrDefault(i => i.Barcode == barcode);
        if (item != null)
        {
            item.Quantity = newQuantity;
            // LineTotal is auto-recalculated by CartItemDto
            RecalculateTotals();
        }
    }

    public void ClearCart()
    {
        CartItems.Clear();
        RecalculateTotals();
    }

    private void RecalculateTotals()
    {
        // Calculate total amount
        _totalAmount = CartItems.Sum(item => item.LineTotal);
        
        // Calculate item count (for weighted items, count as 1 item regardless of weight)
        _itemCount = CartItems.Count;

        OnCartUpdated();
    }

    private void OnCartUpdated()
    {
        CartUpdated?.Invoke(this, EventArgs.Empty);
    }
}
