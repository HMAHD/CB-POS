from decimal import Decimal
from datetime import datetime
from cbpos.core.models import Sale

class ReceiptBuilder:
    """
    Builds the text content for receipts.
    """
    
    WIDTH = 42 # Standard 80mm thermal printer width (approx 42-48 chars)

    @staticmethod
    def build_receipt(sale: Sale) -> str:
        """
        Generate the complete receipt text.
        """
        lines = []
        
        # 1. Header
        lines.append(ReceiptBuilder._center("CEYLON BYTE POS"))
        lines.append(ReceiptBuilder._center("123, Galle Road, Colombo 03"))
        lines.append(ReceiptBuilder._center("Tel: 011-2345678"))
        lines.append(ReceiptBuilder._center(f"VAT Reg: 123456789-7000"))
        lines.append("-" * ReceiptBuilder.WIDTH)
        
        # 2. Meta
        lines.append(f"Receipt: {sale.receipt_no}")
        lines.append(f"Date: {sale.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Cashier: {sale.cashier_id}") # Ideally fetch name
        lines.append("-" * ReceiptBuilder.WIDTH)
        
        # 3. Items
        lines.append(f"{'Item':<20} {'Qty':>5} {'Price':>7} {'Total':>8}")
        lines.append("-" * ReceiptBuilder.WIDTH)
        
        for item in sale.items:
            # Truncate name if too long
            name = item.product.name_en[:20]
            lines.append(f"{name:<20} {item.qty:>5.0f} {item.unit_price:>7.2f} {item.subtotal:>8.2f}")
            
        lines.append("-" * ReceiptBuilder.WIDTH)
        
        # 4. Totals
        lines.append(f"{'TOTAL':<20} {sale.total_amount:>21.2f}")
        lines.append("-" * ReceiptBuilder.WIDTH)
        
        # 5. Tax Breakdown (Backward Calc)
        # Assuming sale.tax_vat and sale.tax_sscl are populated
        lines.append(ReceiptBuilder._center("*** TAX BREAKDOWN ***"))
        lines.append(f"{'VAT (18%)':<20} {sale.tax_vat:>21.2f}")
        lines.append(f"{'SSCL (2.5%)':<20} {sale.tax_sscl:>21.2f}")
        lines.append(f"{'Net Revenue':<20} {sale.net_revenue:>21.2f}")
        lines.append("-" * ReceiptBuilder.WIDTH)
        
        # 6. Footer
        lines.append(ReceiptBuilder._center("Thank You! Come Again."))
        lines.append(ReceiptBuilder._center("Software by Ceylon Byte"))
        lines.append("\n\n") # Feed
        
        return "\n".join(lines)

    @staticmethod
    def _center(text: str) -> str:
        return text.center(ReceiptBuilder.WIDTH)
