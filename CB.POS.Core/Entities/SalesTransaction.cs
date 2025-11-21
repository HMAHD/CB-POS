using System.ComponentModel.DataAnnotations;

namespace CB.POS.Core.Entities;

public class SalesTransaction
{
    public int Id { get; set; }
    
    [Required]
    public DateTime TransactionDate { get; set; } = DateTime.Now;
    
    // Foreign Key to Employee (Cashier)
    public int CashierId { get; set; }
    
    public decimal TotalAmount { get; set; }
    
    [Required]
    public PaymentMethod PaymentMethod { get; set; } = PaymentMethod.Cash;
    
    // Navigation properties
    public Employee Cashier { get; set; } = null!;
    public ICollection<SalesLineItem> LineItems { get; set; } = new List<SalesLineItem>();
}
