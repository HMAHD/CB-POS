# Backward Calculation (Tax Inclusive) vs. the standard Forward Calculation.

### 1. The Concept: "Shelf Price is King"
In the USA or Europe, you see a price tag of **$10.00**. When you go to the counter, the machine adds tax, and you pay **$10.80**.

In Sri Lanka (Retail), if a biscuit packet says **Rs. 100.00 (MRP)**, the customer pays exactly **Rs. 100.00**.
* The tax is **hidden inside** that Rs. 100.
* The shop owner collects Rs. 100, but they don't get to keep all of it. They effectively act as a tax collector for the government.

**Backward Calculation** means taking the Total Cash received (Rs. 100) and doing the math *backwards* to find out how much of that belongs to the government.



[Image of tax inclusive vs exclusive pricing diagram]


### 2. The Math (The "Backward" Formula)

Let's assume the current rates:
* **VAT:** 18%
* **SSCL:** 2.5% (Calculated on 50% of turnover for retail)

Imagine you sell a product for **Rs. 1,180.00**.

#### The Wrong Way (Forward Calculation)
If you think "I made Rs. 1,180, let me pay 18% on that":
* `1180 * 18% = 212.4`
* **Result:** You pay Rs. 212.40 in tax.

#### The Right Way (Backward Calculation)
You assume the Rs. 1,180 *already* represents 118% of the value (100% Base + 18% Tax).
* **Formula:** `Total Price / 1.18`
* `1180 / 1.18 = 1000` (This is your Revenue)
* `1180 - 1000 = 180` (This is the Tax)
* **Result:** You pay Rs. 180.00 in tax.

**Difference:** If you calculate it wrong, you overpay the government by **Rs. 32.40** on a single sale. Over a year, this destroys the business.

### 3. How It Affects Your System

This logic impacts three specific areas of your Python code:

#### A. Database Storage (`sales_transactions` table)
You cannot just store `total_amount`. You must store the breakdown so the owner knows their liability instantly.
When a sale is saved, your **Tax Service** runs silently:
1.  **Input:** `Rs. 100.00`
2.  **Logic:** Calculate VAT portion and SSCL portion.
3.  **Storage:**
    * `total_amount`: 100.00
    * `tax_vat`: 15.25 (Stored for reporting)
    * `tax_sscl`: 1.25 (Stored for reporting)
    * `net_revenue`: 83.50 (This is what the owner actually earned)

#### B. The Receipt (Visuals)
* **For Normal People (B2C):** They just see **Total: Rs. 100.00**. You might print a small footer: *"Prices include VAT/SSCL"*.
* **For Companies (B2B):** If a company buys from you, they need a **Tax Invoice**. Your system needs to print the breakdown (Base Value: 83.50, VAT: 15.25, Total: 100.00) so *they* can claim that VAT back.

#### C. Profit Calculation (The "Real" Profit)
If you buy an item for Rs. 80 and sell it for Rs. 100, do you make Rs. 20 profit?
* **No.**
* You sold it for Rs. 100, but ~Rs. 16 is tax. Your real earnings are ~Rs. 84.
* Your profit is `84 - 80 = Rs. 4`.
* **System Impact:** Your "Profit & Loss" report must use the **Net Revenue**, not the Sales Total, or the owner will think they are richer than they actually are.

### Summary
In your **PRD** and **Tax Service**, "Backward Calculation" simply means:
> *"The user enters the Final Price. The System divides by 1.18 (for VAT) to find the Tax amount and saves it separately."*