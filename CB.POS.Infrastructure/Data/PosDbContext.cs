using CB.POS.Core.Entities;
using Microsoft.EntityFrameworkCore;

namespace CB.POS.Infrastructure.Data;

public class PosDbContext : DbContext
{
    public PosDbContext(DbContextOptions<PosDbContext> options) : base(options)
    {
    }

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        if (!optionsBuilder.IsConfigured)
        {
            optionsBuilder.UseSqlite("Data Source=cbpos.db");
        }
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // Configure Product entity
        modelBuilder.Entity<Product>(entity =>
        {
            // Create unique index on Barcode for fast lookups
            entity.HasIndex(p => p.Barcode)
                .IsUnique();

            // Configure decimal precision for prices
            entity.Property(p => p.Price)
                .HasPrecision(18, 2);
            
            entity.Property(p => p.Cost)
                .HasPrecision(18, 2);

            // Configure relationship with Category
            entity.HasOne(p => p.Category)
                .WithMany(c => c.Products)
                .HasForeignKey(p => p.CategoryId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        // Configure SalesTransaction entity
        modelBuilder.Entity<SalesTransaction>(entity =>
        {
            entity.Property(st => st.TotalAmount)
                .HasPrecision(18, 2);

            // Configure relationship with Employee (Cashier)
            entity.HasOne(st => st.Cashier)
                .WithMany()
                .HasForeignKey(st => st.CashierId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        // Configure SalesLineItem entity
        modelBuilder.Entity<SalesLineItem>(entity =>
        {
            entity.Property(li => li.Quantity)
                .HasPrecision(18, 3); // Support weighted items with 3 decimal places
            
            entity.Property(li => li.UnitPrice)
                .HasPrecision(18, 2);
            
            entity.Property(li => li.LineTotal)
                .HasPrecision(18, 2);

            // Configure relationships
            entity.HasOne(li => li.Transaction)
                .WithMany(t => t.LineItems)
                .HasForeignKey(li => li.TransactionId)
                .OnDelete(DeleteBehavior.Cascade);

            entity.HasOne(li => li.Product)
                .WithMany()
                .HasForeignKey(li => li.ProductId)
                .OnDelete(DeleteBehavior.Restrict);
        });
    }

    // DbSets
    public DbSet<Employee> Employees { get; set; }
    public DbSet<Category> Categories { get; set; }
    public DbSet<Product> Products { get; set; }
    public DbSet<SalesTransaction> SalesTransactions { get; set; }
    public DbSet<SalesLineItem> SalesLineItems { get; set; }
}