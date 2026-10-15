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
