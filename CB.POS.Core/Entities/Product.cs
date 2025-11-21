using System.ComponentModel.DataAnnotations;

namespace CB.POS.Core.Entities;

public class Product
{
    public int Id { get; set; }
    
    [Required]
    [MaxLength(50)]
    public string Barcode { get; set; } = string.Empty; // Indexed, Unique
    
    [Required]
    [MaxLength(200)]
    public string Name { get; set; } = string.Empty;
    
    public decimal Price { get; set; } // Selling price
    
    public decimal Cost { get; set; } // Purchase cost (for profit tracking)
    
    public int StockQuantity { get; set; }
    
    public int LowStockLimit { get; set; } = 10; // Threshold for low stock alerts
    
    public bool IsWeighted { get; set; } = false; // For vegetables/meat sold by weight
    
    // Foreign Key
    public int CategoryId { get; set; }
    
    // Navigation property
    public Category Category { get; set; } = null!;
}
