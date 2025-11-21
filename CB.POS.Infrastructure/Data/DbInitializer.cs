using CB.POS.Core.Entities;
using Microsoft.Extensions.Logging;

namespace CB.POS.Infrastructure.Data;

public class DbInitializer
{
    private readonly PosDbContext _context;
    private readonly ILogger<DbInitializer> _logger;

    public DbInitializer(PosDbContext context, ILogger<DbInitializer> logger)
    {
        _context = context;
        _logger = logger;
    }

    public void Initialize()
    {
        try
        {
            // 1. Ensure Database Exists
            bool created = _context.Database.EnsureCreated();
            
            // 2. Check if we need to seed users
            if (!_context.Employees.Any())
            {
                _logger.LogInformation("Seeding default Admin user...");
                
                _context.Employees.Add(new Employee
                {
                    Name = "Super Admin",
                    Role = "Admin",
                    // In a real app, use a proper hashing algorithm (BCrypt/Argon2). 
                    // For this MVP, we simulate a hash.
                    PinHash = "1234", 
                    PreferredLanguage = "en-US"
                });
                
                _context.SaveChanges();
            }

            // 3. Seed Categories (if not exists)
            if (!_context.Categories.Any())
            {
                _logger.LogInformation("Seeding product categories...");

                var categories = new List<Category>
                {
                    new Category { Name = "Biscuits" },
                    new Category { Name = "Beverages" },
                    new Category { Name = "Essentials" },
                    new Category { Name = "Vegetables" }
                };

                _context.Categories.AddRange(categories);
                _context.SaveChanges();
            }

            // 4. Seed Products (if not exists)
            if (!_context.Products.Any())
            {
                _logger.LogInformation("Seeding Sri Lankan products...");

                // Get category IDs
                var biscuits = _context.Categories.First(c => c.Name == "Biscuits");
                var beverages = _context.Categories.First(c => c.Name == "Beverages");
                var essentials = _context.Categories.First(c => c.Name == "Essentials");
                var vegetables = _context.Categories.First(c => c.Name == "Vegetables");

                var products = new List<Product>
                {
                    // Biscuits
                    new Product
                    {
                        Barcode = "47920240",
                        Name = "Munchee Super Cream Cracker 490g",
                        Price = 650.00m,
                        Cost = 520.00m,
                        StockQuantity = 50,
                        LowStockLimit = 10,
                        CategoryId = biscuits.Id,
                        IsWeighted = false
                    },
                    new Product
                    {
                        Barcode = "47920100",
                        Name = "Maliban Marie 200g",
                        Price = 210.00m,
                        Cost = 170.00m,
                        StockQuantity = 80,
                        LowStockLimit = 15,
                        CategoryId = biscuits.Id,
                        IsWeighted = false
                    },
                    new Product
                    {
                        Barcode = "47920305",
                        Name = "Munchee Lemon Puff 200g",
                        Price = 320.00m,
                        Cost = 260.00m,
                        StockQuantity = 60,
                        LowStockLimit = 10,
                        CategoryId = biscuits.Id,
                        IsWeighted = false
                    },

                    // Beverages
                    new Product
                    {
                        Barcode = "47900001",
                        Name = "Highland Full Cream Milk 1L",
                        Price = 520.00m,
                        Cost = 430.00m,
                        StockQuantity = 40,
                        LowStockLimit = 10,
                        CategoryId = beverages.Id,
                        IsWeighted = false
                    },
                    new Product
                    {
                        Barcode = "47900205",
                        Name = "Milo 400g",
                        Price = 1150.00m,
                        Cost = 950.00m,
                        StockQuantity = 30,
                        LowStockLimit = 8,
                        CategoryId = beverages.Id,
                        IsWeighted = false
                    },
                    new Product
                    {
                        Barcode = "47900350",
                        Name = "Nescafe Classic 100g",
                        Price = 890.00m,
                        Cost = 720.00m,
                        StockQuantity = 25,
                        LowStockLimit = 8,
                        CategoryId = beverages.Id,
                        IsWeighted = false
                    },

                    // Essentials
                    new Product
                    {
                        Barcode = "1001",
                        Name = "Keeris Samba Rice 1kg",
                        Price = 320.00m,
                        Cost = 260.00m,
                        StockQuantity = 100,
                        LowStockLimit = 20,
                        CategoryId = essentials.Id,
                        IsWeighted = false
                    },
                    new Product
                    {
                        Barcode = "8901",
                        Name = "Sunlight Soap 110g",
                        Price = 110.00m,
                        Cost = 85.00m,
                        StockQuantity = 150,
                        LowStockLimit = 30,
                        CategoryId = essentials.Id,
                        IsWeighted = false
                    },
                    new Product
                    {
                        Barcode = "8902",
                        Name = "Signal Toothpaste 120ml",
                        Price = 295.00m,
                        Cost = 230.00m,
                        StockQuantity = 70,
                        LowStockLimit = 15,
                        CategoryId = essentials.Id,
                        IsWeighted = false
                    },
                    new Product
                    {
                        Barcode = "8903",
                        Name = "Vim Dishwash Liquid 500ml",
                        Price = 385.00m,
                        Cost = 310.00m,
                        StockQuantity = 45,
                        LowStockLimit = 10,
                        CategoryId = essentials.Id,
                        IsWeighted = false
                    },

                    // Vegetables (Weighted Items)
                    new Product
                    {
                        Barcode = "2001",
                        Name = "Red Onions (per kg)",
                        Price = 280.00m,
                        Cost = 220.00m,
                        StockQuantity = 50,
                        LowStockLimit = 10,
                        CategoryId = vegetables.Id,
                        IsWeighted = true
                    },
                    new Product
                    {
                        Barcode = "2002",
                        Name = "Potatoes (per kg)",
                        Price = 320.00m,
                        Cost = 250.00m,
                        StockQuantity = 75,
                        LowStockLimit = 15,
                        CategoryId = vegetables.Id,
                        IsWeighted = true
                    }
                };

                _context.Products.AddRange(products);
                _context.SaveChanges();

                _logger.LogInformation($"Successfully seeded {products.Count} products.");
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An error occurred while initializing the database.");
            throw; // Vital failure, let the app crash or handle upstream
        }
    }
}