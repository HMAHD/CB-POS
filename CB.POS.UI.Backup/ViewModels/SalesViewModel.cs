using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CB.POS.Core.DTOs;
using CB.POS.Core.Interfaces.Services;
using CB.POS.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.UI.Xaml.Controls;
using System;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace CB.POS.UI.ViewModels;

/// <summary>
/// ViewModel for the Sales/POS screen.
/// This is the "brain" of the point-of-sale interface.
/// </summary>
public partial class SalesViewModel : ObservableObject
{
    private readonly ICartService _cartService;
    private readonly PosDbContext _context;

    [ObservableProperty]
    private string _inputBarcode = "";

    [ObservableProperty]
    private string _errorMessage = "";

    [ObservableProperty]
    private CartItemDto? _selectedCartItem;

    // Expose cart service's observable collection directly
    public ObservableCollection<CartItemDto> CartItems => _cartService.CartItems;

    // Computed properties that update when cart changes
    public string TotalDisplay => $"Rs. {_cartService.TotalAmount:N2}";
    public int ItemCount => _cartService.ItemCount;

    public SalesViewModel(ICartService cartService, PosDbContext context)
    {
        _cartService = cartService;
        _context = context;

        // Subscribe to cart updates to refresh UI properties
        _cartService.CartUpdated += OnCartUpdated;
    }

    private void OnCartUpdated(object? sender, EventArgs e)
    {
        // Notify UI that computed properties have changed
        OnPropertyChanged(nameof(TotalDisplay));
        OnPropertyChanged(nameof(ItemCount));
    }

    /// <summary>
    /// Process barcode scan - triggered when user presses Enter in barcode input
    /// </summary>
    [RelayCommand]
    private async Task ProcessScanAsync()
    {
        // Clear previous error
        ErrorMessage = "";

        // Validate input
        if (string.IsNullOrWhiteSpace(InputBarcode))
        {
            return; // Silently ignore empty input
        }

        try
        {
            // Search for product by barcode
            var product = await _context.Products
                .Include(p => p.Category)
                .FirstOrDefaultAsync(p => p.Barcode == InputBarcode.Trim());

            if (product != null)
            {
                // Product found - add to cart
                // For weighted items, default to 1, user can modify with F3
                decimal quantity = 1m;
                
                _cartService.AddItem(product, quantity);

                // Clear input for next scan
                InputBarcode = "";
            }
            else
            {
                // Product not found
                ErrorMessage = "Product not found. Please try again.";
                
                // Note: System beep not implemented in WinUI 3 yet
                // Future: Add custom sound feedback

                // Clear input
                InputBarcode = "";
            }
        }
        catch (Exception ex)
        {
            ErrorMessage = $"Error: {ex.Message}";
            // Note: System sound not implemented in WinUI 3 yet
        }
    }

    /// <summary>
    /// Remove selected item from cart - triggered by F4 or Void button
    /// </summary>
    [RelayCommand]
    private void VoidItem()
    {
        if (SelectedCartItem != null)
        {
            _cartService.RemoveItem(SelectedCartItem.Barcode);
            SelectedCartItem = null;
            ErrorMessage = "";
        }
    }

    /// <summary>
    /// Process payment - placeholder for now
    /// </summary>
    [RelayCommand]
    private async Task PayAsync()
    {
        if (CartItems.Count == 0)
        {
            ErrorMessage = "Cart is empty. Please add items first.";
            // Note: System sound not implemented in WinUI 3 yet
            return;
        }

        var dialog = new ContentDialog
        {
            Title = "Payment",
            Content = $"Total Amount: Rs. {_cartService.TotalAmount:N2}\n\nPayment processing coming soon...",
            CloseButtonText = "OK",
            XamlRoot = App.MainWindow.Content.XamlRoot
        };
        await dialog.ShowAsync();
    }

    /// <summary>
    /// Search for product - placeholder for future enhancement
    /// </summary>
    [RelayCommand]
    private async Task SearchProductAsync()
    {
        var dialog = new ContentDialog
        {
            Title = "Product Search",
            Content = "Product search feature coming soon...",
            CloseButtonText = "OK",
            XamlRoot = App.MainWindow.Content.XamlRoot
        };
        await dialog.ShowAsync();
    }

    /// <summary>
    /// Change quantity of selected item - placeholder for future enhancement
    /// </summary>
    [RelayCommand]
    private async Task ChangeQuantityAsync()
    {
        if (SelectedCartItem == null)
        {
            ErrorMessage = "Please select an item first.";
            return;
        }

        // Placeholder dialog for quantity change
        var dialog = new ContentDialog
        {
            Title = "Change Quantity",
            Content = $"Current quantity: {SelectedCartItem.Quantity}\n\nQuantity modification coming soon...",
            CloseButtonText = "OK",
            XamlRoot = App.MainWindow.Content.XamlRoot
        };
        await dialog.ShowAsync();
    }

    /// <summary>
    /// Focus barcode input - triggered by F1
    /// </summary>
    [RelayCommand]
    private void FocusBarcode()
    {
        // This will be handled in the View's code-behind
        // The command exists for keyboard accelerator binding
    }
}
