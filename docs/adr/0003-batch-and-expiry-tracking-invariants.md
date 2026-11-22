# Batch and Expiry Tracking Invariants and FEFO Allocation

## Context
In grocery, bakery, and pharmacy retail in Sri Lanka, products often carry manufacturer lot/batch numbers and expiration dates. The same product may sit on the shelf at two different Maximum Retail Prices (MRPs) following gazetted price adjustments, tax revisions, or manufacturer updates. Under the Consumer Affairs Authority Act No. 9 of 2003 and NMRA Act No. 5 of 2015, charging more than the printed MRP is illegal. Furthermore, stock must be rotated using First-Expiry-First-Out (FEFO) to minimize spoilage and prevent selling expired goods.

Earlier implementations tracked stock exclusively at the aggregate `Product.stock_qty` level, which prevented per-lot tracing, per-batch pricing, and expiry alerts.

## Decision
1. **The Invariant:** For every product where `tracks_batches` is enabled, the sum of all active and inactive batch quantities on hand must at all times equal the product's authoritative stock quantity:
   $$\sum_{b \in \text{batches}} b.\text{qty\_on\_hand} = \text{Product.stock\_qty}$$
   Every stock mutation on a batch-tracked product (sale, void, refund, purchase GRN, stock adjustment, stock count) writes a `StockMovement` capturing both `product_id` and `batch_id`.
2. **Base-Unit Truth:** All quantities and costs on `ProductBatch` are strictly stored in **base units** (e.g. pieces), reconciling with Phase 10B.3 (#937) unit conversion where `base_qty = purchase_qty * factor` and `base_cost = purchase_unit_cost / factor`.
3. **FEFO Allocation & Row Locking:** Automated stock deduction prioritizes batches in strict order: `expiry_date ASC NULLS LAST`, `received_at ASC`, `id ASC`. On PostgreSQL network mode, eligible batches are locked using `SELECT ... FOR UPDATE` in deterministic order to eliminate multi-till concurrency races. If line quantity spans multiple batches, the sale splits into distinct `SaleItem` rows. If negative stock is permitted by shop configuration and all batch stock is exhausted, the newest active batch absorbs the negative balance to maintain the invariant.
4. **Shelf MRP Truth & CAA Compliance:** If a batch defines `mrp`, that MRP establishes the line's `original_price` and default `unit_price`. Discounts and promotions reduce from this MRP. Overrides exceeding `batch.mrp` are blocked without manager override. If active batches carry differing MRPs, a lightweight picker enables the cashier to match the physical box brought to the checkout counter.
5. **Traceable Returns:** Sale voids and customer refunds return stock strictly to the originating `SaleItem.batch_id` using `StockMovement(type='RETURN'/'VOID', batch_id=...)`. Foreign key `RESTRICT` prevents deletion of referenced batches. If a batch was deactivated or had zero stock, incoming returns automatically reactivate it (`is_active = True`).
6. **Stock Count Accountability:** Physical stock counts for tracked products are conducted per batch, recording counted quantities against specific batches so batch variances are directly audited without arbitrary silent re-allocation.
7. **Catalog Authority & LAN Sync:** Batches are catalog entities created and edited exclusively on the Main PC (`require_catalog_writable`) and synchronized to tills via sync protocol 1.7. Tills push sales with `batch_id`; offline till overdrafts are absorbed by the Main PC as negative batch balances with a `BATCH_OVERDRAFT_SYNC_CONFLICT` audit log entry, never retroactively invalidating completed sales.

