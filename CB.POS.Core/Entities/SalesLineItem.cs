using System.ComponentModel.DataAnnotations;

namespace CB.POS.Core.Entities;

public class SalesLineItem
{
    public int Id { get; set; }
    
    // Foreign Keys
    public int TransactionId { get; set; }
    public int ProductId { get; set; }
    
    // Decimal quantity to support weighted items (e.g., 2.5 kg)
    public decimal Quantity { get; set; }
    
    public decimal UnitPrice { get; set; } // Price at time of sale
    
    // Computed property: Quantity * UnitPrice
    public decimal LineTotal { get; set; }
    
    // Navigation properties
    public SalesTransaction Transaction { get; set; } = null!;
    public Product Product { get; set; } = null!;
}
