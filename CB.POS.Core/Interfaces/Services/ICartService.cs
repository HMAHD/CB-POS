using CB.POS.Core.DTOs;
using CB.POS.Core.Entities;
using System.Collections.ObjectModel;

namespace CB.POS.Core.Interfaces.Services;

/// <summary>
/// Interface for managing the shopping cart in the POS system.
/// This is the "brain" of the POS screen - manages the current sale in memory.
/// </summary>
public interface ICartService
{
    /// <summary>
    /// Observable collection of items currently in the cart.
    /// Bound to the UI for automatic updates.
    /// </summary>
    ObservableCollection<CartItemDto> CartItems { get; }

    /// <summary>
    /// Total amount for all items in the cart.
    /// </summary>
    decimal TotalAmount { get; }

    /// <summary>
    /// Total number of items in the cart (sum of all quantities).
    /// </summary>
    int ItemCount { get; }

    /// <summary>
    /// Event raised when the cart is updated (item added/removed/modified).
    /// </summary>
    event EventHandler? CartUpdated;

    /// <summary>
    /// Adds a product to the cart. If the product already exists, increases the quantity.
    /// </summary>
    /// <param name="product">The product to add</param>
    /// <param name="quantity">Quantity to add (default 1, can be decimal for weighted items)</param>
    void AddItem(Product product, decimal quantity = 1);

    /// <summary>
    /// Removes an item from the cart by barcode.
    /// </summary>
    /// <param name="barcode">The barcode of the item to remove</param>
    void RemoveItem(string barcode);

    /// <summary>
    /// Updates the quantity of an item in the cart.
    /// </summary>
    /// <param name="barcode">The barcode of the item to update</param>
    /// <param name="newQuantity">The new quantity</param>
    void UpdateQuantity(string barcode, decimal newQuantity);

    /// <summary>
    /// Clears all items from the cart.
    /// </summary>
    void ClearCart();
}
