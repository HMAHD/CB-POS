using System.ComponentModel.DataAnnotations;

namespace CB.POS.Core.Entities;

public class Category
{
    public int Id { get; set; }
    
    [Required]
    [MaxLength(100)]
    public string Name { get; set; } = string.Empty;
    
    // Navigation property
    public ICollection<Product> Products { get; set; } = new List<Product>();
}
