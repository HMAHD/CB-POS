"""Generate sample trilingual invoices for visual inspection and verification (#924)."""

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Force offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cbpos.core.models import Customer, Product, Sale, SaleItem, SalePayment, Unit
from cbpos.core.models.tax_invoice import TaxInvoice, TaxInvoiceLine
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.tax_invoice_pdf_builder import TaxInvoicePDFBuilder

out_dir = Path("docs/remediation/sample_pdfs")
out_dir.mkdir(parents=True, exist_ok=True)

# Mock settings
ConfigService.set("shop_name", "Lanka Super Centre / ලංකා සුපර් සෙන්ටර්")
ConfigService.set("shop_address", "No. 45, Galle Road, Colombo 03, Sri Lanka")
ConfigService.set("shop_phone", "+94 11 234 5678")
ConfigService.set("vat_registered", True)
ConfigService.set("vat_number", "123456789-7000")
ConfigService.set("company_tax_id", "123456789")
ConfigService.set("company_bank_name", "Bank of Ceylon")
ConfigService.set("company_account_number", "000123456789")
ConfigService.set("company_bank_branch", "Corporate Branch, Colombo")

kg = Unit(name="Kilogram", abbreviation="kg", decimal_places=3)
cement = Product(
    name_en="Elephant Cement 50kg", name_si="අලි කොට්ට සිමෙන්ති 50kg", name_ta="யானை சிமெண்ட் 50kg", price=Decimal("2450.00")
)
tea = Product(
    name_en="Ceylon BOPF Tea 500g", name_si="ශ්‍රී ලංකා තේ 500g", name_ta="இலங்கை தேயிலை 500g", price=Decimal("1200.00")
)
sugar = Product(name_en="White Sugar", name_si="සුදු සීනි", name_ta="வெள்ளை சர்க்கரை", price=Decimal("260.00"), unit=kg)

for lang in ["en", "si", "ta"]:
    ConfigService.set("receipt_language", lang)

    cust_name = {
        "en": "Perera & Sons Enterprises",
        "si": "පෙරේරා සහ පුත්‍රයෝ ව්‍යාපාරිකයෝ",
        "ta": "பெரேரா அண்ட் சன்ஸ் வர்த்தகம்",
    }[lang]

    cust_addr = {
        "en": "12 Kandy Road, Kiribathgoda",
        "si": "නො. 12, නුවර පාර, කිරිබත්ගොඩ",
        "ta": "12 கண்டி வீதி, கிரிபத்கொடை",
    }[lang]

    sale = Sale(
        document_number=f"INV-2026-{lang.upper()}-001",
        date=datetime(2026, 11, 19, 14, 30),
        total_amount=Decimal("6360.00"),
        tax_vat=Decimal("970.17"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("5389.83"),
        payment_method="CASH",
        status="COMPLETED",
        customer=Customer(
            name=cust_name,
            address=cust_addr,
            vat_number="987654321-7000",
            tax_id="987654321",
        ),
    )
    sale.items = [
        SaleItem(product=cement, qty=Decimal("2.000"), unit_price=Decimal("2450.00"), subtotal=Decimal("4900.00")),
        SaleItem(product=tea, qty=Decimal("1.000"), unit_price=Decimal("1200.00"), subtotal=Decimal("1200.00")),
        SaleItem(product=sugar, qty=Decimal("1.000"), unit_price=Decimal("260.00"), subtotal=Decimal("260.00")),
    ]
    sale.payments = [SalePayment(payment_method="CASH", amount=Decimal("6360.00"))]

    comm_path = out_dir / f"commercial_invoice_{lang}.pdf"
    InvoiceService.generate_pdf(sale, str(comm_path))
    print(f"Generated {comm_path}")

    # Tax Invoice
    tax_inv = TaxInvoice(
        id=1,
        sale_id=sale.id,
        serial=f"26NOV_{lang.upper()}_00001",
        issued_at=datetime(2026, 11, 19, 14, 30),
        supply_date=date(2026, 11, 19),
        payment_method="CASH",
        supplier_name="සීමාසහිත ලංකා වෙළඳ සමාගම (Lanka Super Centre Ltd)",
        supplier_address="No. 45, Galle Road, Colombo 03",
        supplier_phone="+94 11 234 5678",
        supplier_tin="123456789",
        buyer_name=cust_name,
        buyer_address=cust_addr,
        buyer_phone="+94 77 123 4567",
        buyer_tin="987654321",
        issue_language=lang,
        print_count=0,
        subtotal_amount=Decimal("6360.00"),
        discount_amount=Decimal("0.00"),
        net_amount=Decimal("5389.83"),
        tax_vat=Decimal("970.17"),
        total_amount=Decimal("6360.00"),
        amount_in_words="Six Thousand Three Hundred Sixty Rupees Only",
        lines=[
            TaxInvoiceLine(
                item_number=1,
                product_id=1,
                item_code_snapshot="CEM-001",
                product_name_snapshot={
                    "en": "Elephant Cement 50kg",
                    "si": "අලි කොට්ට සිමෙන්ති 50kg (Cement)",
                    "ta": "யானை சிமெண்ட் 50kg (Cement)",
                }[lang],
                unit_snapshot="bag",
                quantity=Decimal("2.000"),
                unit_price=Decimal("2450.00"),
                discount_amount=Decimal("0.00"),
                net_amount=Decimal("4152.54"),
                vat_rate=Decimal("18.00"),
                vat_amount=Decimal("747.46"),
                total_amount=Decimal("4900.00"),
            ),
            TaxInvoiceLine(
                item_number=2,
                product_id=2,
                item_code_snapshot="TEA-001",
                product_name_snapshot={
                    "en": "Ceylon BOPF Tea 500g",
                    "si": "ශ්‍රී ලංකා තේ 500g (Ceylon Tea)",
                    "ta": "இலங்கை தேயிலை 500g (Tea)",
                }[lang],
                unit_snapshot="pkt",
                quantity=Decimal("1.000"),
                unit_price=Decimal("1200.00"),
                discount_amount=Decimal("0.00"),
                net_amount=Decimal("1016.95"),
                vat_rate=Decimal("18.00"),
                vat_amount=Decimal("183.05"),
                total_amount=Decimal("1200.00"),
            ),
        ],
    )
    tax_path = out_dir / f"tax_invoice_{lang}.pdf"
    TaxInvoicePDFBuilder.generate_pdf(tax_inv, str(tax_path))
    print(f"Generated {tax_path}")
