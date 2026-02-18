# One-Click Data Migration Guide
## From Standalone (SQLite) to Network (PostgreSQL)

---

## 🎯 The Challenge

**Problem**: Non-technical shop owners need to migrate from a single-terminal setup (SQLite) to a multi-terminal network setup (PostgreSQL) without:
- Losing any data (products, customers, sales history)
- Manual database configuration
- Command-line operations
- Technical knowledge

**Solution**: **One-Click Migration** - A friendly button that automatically transfers all local data to the network server.

---

## 🚀 How It Works (User Perspective)

### Step 1: Install PostgreSQL on Server
**One-time setup** (can be done by an IT person or using installer):
```bash
# Windows: Download and run PostgreSQL installer from postgresql.org
# macOS: brew install postgresql
# Linux: sudo apt-get install postgresql
```

Create an empty database:
```sql
-- Connect to PostgreSQL as admin user
CREATE DATABASE cbpos;
CREATE USER cbpos_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE cbpos TO cbpos_user;
```

### Step 2: Configure Network Settings in CB-POS
1. **Open Application** → Settings → Network tab
2. **Fill in Connection Details**:
   - Host: `192.168.1.100` (server IP address)
   - Port: `5432` (default PostgreSQL port)
   - Database Name: `cbpos`
   - Username: `cbpos_user`
   - Password: `secure_password`
3. **Click "Test Connection"** → Should show "✓ Connection successful"

### Step 3: Click "Upload Local Data to Server" 🚀
1. Click the green **"🚀 Upload Local Data to Server"** button
2. Confirm the migration dialog (shows target server details)
3. Wait for progress dialog (usually 30-60 seconds for typical shop data)
4. See success message with record count
5. **Save** network settings
6. **Restart** the application

### Step 4: Done!
- Application now connects to PostgreSQL server
- All data is preserved (products, customers, sales, etc.)
- Multiple terminals can connect to the same server
- Each terminal sees real-time data updates

---

## 🔧 Technical Implementation

### Architecture Overview

```
┌─────────────────────┐
│   User clicks       │
│  "Upload Data"      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│    NetworkPage._migrate_data()          │
│  - Validates inputs                     │
│  - Shows confirmation dialog            │
│  - Calls MigrationService               │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│  MigrationService.migrate_sqlite_       │
│  to_postgres()                          │
│                                         │
│  1. Test connections                    │
│  2. Verify target DB is empty           │
│  3. Create schema (all tables)          │
│  4. Copy data (preserve IDs)            │
│  5. Reset PostgreSQL sequences          │
└─────────────────────────────────────────┘
```

### Migration Order (Respects Foreign Keys)

Tables are migrated in dependency order:

1. **Auth & Permissions**: Role, Permission, User
2. **Master Data**: VoidReason, Category, Supplier, Customer, CustomerContact, PriceList
3. **Products**: Product, PriceListItem, CompositeItem
4. **Promotions**: Promotion
5. **Transactions**: Sale, SaleItem, SalePayment, Purchase, PurchaseItem
6. **Inventory**: StockMovement
7. **System**: AuditLog, SuspendedTransaction, Shift, CashMovement

### Key Features

#### 1. **ID Preservation**
```python
# Uses merge() to preserve primary keys
for record in records:
    src_session.expunge(record)  # Detach from source
    tgt_session.merge(record)    # Merge into target (keeps ID)
```

**Why it matters**: Sales records reference products by ID. If IDs change, relationships break.

#### 2. **Sequence Reset (PostgreSQL)**
```python
# After bulk insert with explicit IDs, sequences are out of sync
# Reset to max(id) + 1 to prevent duplicates on next insert
seq_query = text(f"SELECT pg_get_serial_sequence('{table_name}', 'id')")
result = tgt_session.execute(seq_query)
seq_name = result.scalar()

if seq_name:
    reset_query = text(f"SELECT setval('{seq_name}', "
                      f"COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, false)")
    tgt_session.execute(reset_query)
```

**Why it matters**: Without this, the next sale would try to use ID=1, which already exists → error.

#### 3. **Empty Database Check**
```python
# Check if target has existing data
for table in ["users", "products", "sales", "customers"]:
    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
    count = result.scalar()
    if count > 0:
        return False, f"Table '{table}' has {count} rows. Use empty database."
```

**Why it matters**: Prevents accidental data overwrite or ID conflicts.

---

## 📊 What Gets Migrated

### Complete Data Transfer

| Category | Tables | Sample Record Count (Typical Shop) |
|----------|--------|-------------------------------------|
| **Auth** | roles, permissions, users | ~10 records |
| **Products** | products, categories, price_lists | 500-5000 products |
| **Customers** | customers, customer_contacts | 100-1000 customers |
| **Suppliers** | suppliers, product_suppliers | 10-50 suppliers |
| **Sales History** | sales, sale_items, sale_payments | 1000-10000+ transactions |
| **Inventory** | stock_movements, composite_items | 1000-50000 movements |
| **System Data** | audit_log, shifts, cash_movements | Variable |

**Estimated Migration Time**:
- Small shop (500 products, 1000 sales): **~30 seconds**
- Medium shop (2000 products, 5000 sales): **~60 seconds**
- Large shop (5000 products, 20000 sales): **~2-3 minutes**

---

## 🛡️ Safety Features

### Pre-Migration Checks
1. ✅ **Connection Test**: Both source and target must be accessible
2. ✅ **Empty Database Validation**: Target must be empty (no accidental overwrites)
3. ✅ **User Confirmation**: Shows detailed dialog with target server info
4. ✅ **Schema Creation**: Automatically creates all tables with correct structure

### Error Handling
- **Connection Failure**: Clear error message with specific issue
- **Data Validation**: SQLAlchemy validates all relationships during merge
- **Rollback on Failure**: If migration fails mid-way, target database is rolled back
- **Progress Indicator**: User knows something is happening (not frozen)

### Post-Migration Verification
```python
# Service provides table counts for verification
success, counts = MigrationService.get_table_counts(postgres_url)
# Returns: {'products': 500, 'customers': 120, 'sales': 1250, ...}
```

---

## 🎨 User Interface

### Dark Theme
- **Migration Group**: Green accent (#39FF14 - neon green)
- **Upload Button**: Bright green background, bold text, rocket emoji
- **Info Label**: Light gray text on transparent background

### Light Theme
- **Migration Group**: Emerald accent (#10B981 - professional green)
- **Upload Button**: Emerald green background, white text
- **Info Label**: Gray text for readability

### Visual Hierarchy
```
Network Settings
├── Database Mode: [Standalone ▼]
│
├── Network Database Credentials (hidden in Standalone)
│   ├── Host IP: [192.168.1.100]
│   ├── Port: [5432]
│   ├── Database Name: [cbpos]
│   ├── Username: [cbpos_user]
│   └── Password: [••••••••]
│
├── [Test Connection] (cyan outline button)
│
├── One-Click Data Migration (green border)
│   ├── ℹ️ Info text explaining what happens
│   └── [🚀 Upload Local Data to Server] (green button)
│
└── ⚠ Warning: Restart required
```

---

## 🧪 Testing the Migration

### Test Scenario 1: Fresh Migration
1. **Setup**:
   - Install PostgreSQL
   - Create empty database `cbpos_test`
   - Configure network settings in CB-POS

2. **Execute**:
   - Click "Upload Local Data to Server"
   - Confirm dialog

3. **Verify**:
   ```sql
   -- Check record counts match
   SELECT COUNT(*) FROM products;  -- Should match local count
   SELECT COUNT(*) FROM sales;     -- Should match local count

   -- Verify relationships intact
   SELECT s.id, s.document_number, p.name_en
   FROM sales s
   JOIN sale_items si ON s.id = si.sale_id
   JOIN products p ON si.product_id = p.id
   LIMIT 5;  -- Should return valid data
   ```

4. **Test New Sale**:
   - Make a sale on Terminal 1
   - Verify it appears immediately on Terminal 2
   - Check ID sequence works (no duplicate key errors)

### Test Scenario 2: Empty Database Check
1. **Setup**: Use PostgreSQL database that already has data
2. **Execute**: Click "Upload Local Data to Server"
3. **Expected**: Error message: "Table 'products' has X rows. Please use an empty database."

### Test Scenario 3: Connection Failure
1. **Setup**: Enter wrong password
2. **Execute**: Click "Upload Local Data to Server"
3. **Expected**: Error dialog with connection failure details

---

## 🔍 Troubleshooting

### Issue 1: "Target database is not empty"
**Cause**: PostgreSQL database has existing data

**Solution**:
```sql
-- Option A: Drop and recreate database (CAUTION: loses data)
DROP DATABASE cbpos;
CREATE DATABASE cbpos;
GRANT ALL PRIVILEGES ON DATABASE cbpos TO cbpos_user;

-- Option B: Drop all tables
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO cbpos_user;
```

### Issue 2: "Connection failed: password authentication failed"
**Cause**: Incorrect username or password

**Solution**:
1. Verify credentials: `psql -U cbpos_user -d cbpos -h 192.168.1.100`
2. Reset password if needed:
   ```sql
   ALTER USER cbpos_user WITH PASSWORD 'new_password';
   ```

### Issue 3: "Migration failed: duplicate key value violates unique constraint"
**Cause**: IDs already exist in target database (shouldn't happen with empty DB check)

**Solution**:
1. Ensure target database is completely empty
2. Check no other process is inserting data during migration
3. Re-run migration on clean database

### Issue 4: Migration hangs or times out
**Cause**: Network issues or very large database

**Solution**:
1. Check network connectivity: `ping 192.168.1.100`
2. Check PostgreSQL is accepting connections: `telnet 192.168.1.100 5432`
3. For very large databases (>100k records), consider manual migration:
   ```bash
   pg_dump --data-only sqlite_dump.sql
   psql -U cbpos_user -d cbpos < sqlite_dump.sql
   ```

---

## 📈 Performance Optimization

### For Large Databases

If migration takes >5 minutes:

1. **Batch Insert** (future enhancement):
   ```python
   # Instead of individual merge()
   tgt_session.bulk_save_objects(records, preserve_order=False)
   ```

2. **Disable Indexes Temporarily**:
   ```sql
   -- Before migration
   DROP INDEX IF EXISTS idx_products_barcode;

   -- After migration
   CREATE INDEX idx_products_barcode ON products(barcode);
   ```

3. **Increase PostgreSQL Performance**:
   ```ini
   # postgresql.conf
   shared_buffers = 256MB
   work_mem = 16MB
   maintenance_work_mem = 128MB
   ```

---

## 🔐 Security Considerations

### Network Configuration
- **Firewall**: Ensure port 5432 is open for internal network only
- **SSL/TLS**: For production, enable SSL connections:
  ```python
  postgres_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"
  ```

### Password Storage
- Settings are stored in `settings.json` (plain text)
- **Recommendation**: Use environment variables for production:
  ```python
  import os
  password = os.getenv("CBPOS_DB_PASSWORD", ConfigService.get("network_db_password"))
  ```

### Access Control
```sql
-- Limit user to only cbpos database
REVOKE ALL ON DATABASE postgres FROM cbpos_user;
GRANT CONNECT ON DATABASE cbpos TO cbpos_user;
```

---

## 📚 Code Reference

### Files Modified
1. **cbpos/core/services/migration_service.py** (NEW)
   - `MigrationService.migrate_sqlite_to_postgres()` - Main migration logic
   - `MigrationService.get_table_counts()` - Verification helper

2. **cbpos/ui/views/settings_pages.py**
   - `NetworkPage.init_ui()` - Added migration UI group
   - `NetworkPage._migrate_data()` - Migration button handler
   - `NetworkPage._on_mode_changed()` - Show/hide migration group

3. **cbpos/ui/styles/dark.qss** & **light.qss**
   - `#NetworkMigrationGroup` - Green bordered group box
   - `#BtnMigrate` - Green button styling
   - `#MigrationInfoLabel` - Info text styling

---

## 🎓 For Developers

### Adding New Tables to Migration

If you add a new model, update `MIGRATION_ORDER` in `migration_service.py`:

```python
MIGRATION_ORDER = [
    # ... existing tables ...
    YourNewModel,  # Add at appropriate dependency level
]
```

**Rules**:
1. Tables with no foreign keys go first
2. Tables with foreign keys go after their dependencies
3. Junction tables (many-to-many) go after both related tables

### Custom Migration Logic

For special cases (e.g., data transformation):

```python
def migrate_with_transform(sqlite_url, postgres_url):
    # ... standard migration setup ...

    # Custom logic for specific table
    old_products = src_session.query(OldProductModel).all()
    for old_prod in old_products:
        new_prod = NewProductModel(
            id=old_prod.id,
            name=old_prod.name.upper(),  # Transform
            price=old_prod.price * 1.18,  # Add tax
        )
        tgt_session.add(new_prod)
```

---

## ✅ Success Criteria

Migration is successful when:

1. ✅ All record counts match between source and target
2. ✅ New sales can be created without ID conflicts
3. ✅ Relationships are intact (can query sales → products)
4. ✅ Multiple terminals can connect simultaneously
5. ✅ Real-time data synchronization works
6. ✅ No data loss (verify via sample queries)

**Verification Checklist**:
```sql
-- 1. Check counts
SELECT 'products' as table_name, COUNT(*) FROM products
UNION ALL
SELECT 'customers', COUNT(*) FROM customers
UNION ALL
SELECT 'sales', COUNT(*) FROM sales;

-- 2. Test relationships
SELECT s.document_number, c.name, COUNT(si.id) as items
FROM sales s
LEFT JOIN customers c ON s.customer_id = c.id
LEFT JOIN sale_items si ON s.id = si.sale_id
GROUP BY s.id, s.document_number, c.name
LIMIT 10;

-- 3. Verify sequences
SELECT last_value FROM products_id_seq;  -- Should be > max(id)
SELECT last_value FROM sales_id_seq;     -- Should be > max(id)
```

---

## 🚀 Future Enhancements

### Phase 2 Features (Potential)
1. **Incremental Migration**: Only sync new records since last migration
2. **Bidirectional Sync**: Keep SQLite as backup, sync back from PostgreSQL
3. **Automatic Database Creation**: App creates `cbpos` database if doesn't exist
4. **Migration Preview**: Show what will be migrated before executing
5. **Rollback Feature**: Restore SQLite backup if migration fails
6. **Progress Bars**: Show per-table progress (15% products, 45% sales, etc.)
7. **Migration Logs**: Save detailed log file for troubleshooting

---

**One-Click Migration: Making Enterprise Technology Accessible to Everyone** ✨
