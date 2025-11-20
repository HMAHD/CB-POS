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
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An error occurred while initializing the database.");
            throw; // Vital failure, let the app crash or handle upstream
        }
    }
}