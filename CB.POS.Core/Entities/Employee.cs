using System.ComponentModel.DataAnnotations;

namespace CB.POS.Core.Entities;

public class Employee
{
    public int Id { get; set; }
    
    [Required]
    public string Name { get; set; } = string.Empty;
    
    [Required]
    public string Role { get; set; } = "Cashier"; // "Admin", "Cashier", "Manager"
    
    [Required]
    public string PinHash { get; set; } = string.Empty; // Never store plain PINs!
    
    public bool IsActive { get; set; } = true;
    
    // For Localization preference (Optional)
    public string PreferredLanguage { get; set; } = "en-US"; 
}