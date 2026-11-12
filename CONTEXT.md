# CB POS

Point of sale for small and medium Sri Lankan shops: checkout, stock, customers and credit, run on one PC or as a Main PC with tills over LAN Sync.

## Language

### Loyalty

**Loyalty Points**:
Whole-number reward a **Customer** builds up from purchases and can spend on later bills.
_Avoid_: rewards, credits (Credit means the customer's debt book), stars

**Earn**:
Points added for a completed sale: one point per **Points Ratio** rupees of the **Final Bill**, only when a Customer is attached and loyalty is enabled.
_Avoid_: accrue, award (in UI text)

**Points Ratio**:
Rupees a customer must spend to earn one point (setting, default 100).
_Avoid_: earn rate, multiplier

**Final Bill**:
What the customer pays for a sale after line discounts, the bill discount and any **Redeemed** points; the amount points are earned on.
_Avoid_: net, subtotal (Sub Total means the sum of line amounts on documents)

**Redeem**:
Spend points at checkout as a rupee discount on the current bill, at the **Point Value**, never more than the bill.
_Avoid_: cash in, use points as payment

**Point Value**:
Rupee value of one point when redeemed (setting).

**Minimum Redeem**:
Fewest points a customer must hold before they can redeem (setting).

**Points Adjustment**:
A manager's manual change to a customer's points, with a reason, permission-gated and audited.
_Avoid_: correction, override

**Points History**:
The per-customer list of every points change (earn, redeem, reversal, adjustment); the customer's points figure always equals its running total.
_Avoid_: points log, ledger (in UI text; "loyalty ledger" is fine in code)

### Credit

**Credit**:
A customer's debt to the shop from sales put on their book, tracked in the Credit Book.
_Avoid_: loyalty, store credit

### Payments & Refunds

**Payment Kind**:
The method used to settle a bill or refund (Cash, Card, Credit, QR/Bank Transfer). Each payment record tracks its kind and amount.
_Avoid_: tender type (in UI text), payment mode

**Refund State**:
The refund status of a sale: `NONE` (no items refunded), `PARTIAL` (some items or quantities returned), or `FULL` (entire bill refunded).
_Avoid_: return status, voided (Void means canceling an unpaid cart before completion)

### Tax & Compliance

**Tax Invoice**:
A formal VAT document issued on demand to VAT-registered buyers complying with statutory 2026 mandates: unique serial (`YYMMM_QQQQ_XXXXX`), supplier/buyer particulars, VAT breakdown, and `ORIGINAL` or `COPY ONLY` markings.
_Avoid_: tax bill, retail receipt (Retail receipts are separate proof-of-purchase documents and never say "TAX INVOICE")

### Architecture & Synchronization

**Schema Owner**:
The designated migration authority (in PostgreSQL network mode or standalone SQLite) that runs Alembic database migrations to HEAD. Secondary terminals verify schema compatibility but do not mutate database structure.
_Avoid_: migration master, database leader

**Till Identity**:
A unique identifier (`TERM-01`, `TERM-02`, etc.) assigned to each physical till terminal, stamped on every generated transaction and audit entry (`origin_terminal_id`) to maintain clear provenance across multi-terminal setups.
_Avoid_: register number, machine name
