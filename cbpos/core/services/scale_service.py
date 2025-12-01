from decimal import Decimal
from typing import Dict, Optional


class ScaleService:
    """
    Service for parsing price-embedded barcodes from electronic scales.
    Supports EAN-13 format with configurable prefix and decimal places.

    Standard Format: PP IIIII WWWWW C
    - PP: Prefix (default '20')
    - IIIII: Product ID (5 digits)
    - WWWWW: Weight/Price (5 digits)
    - C: Checksum (1 digit)
    """

    # Default configuration
    DEFAULT_PREFIX = "20"
    DEFAULT_DECIMAL_PLACES = 3

    @staticmethod
    def parse_barcode(
        barcode: str,
        prefix: Optional[str] = None,
        decimal_places: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Parse a price-embedded barcode from an electronic scale.

        Args:
            barcode (str): The 13-digit EAN-13 barcode
            prefix (str, optional): Expected prefix (default '20')
            decimal_places (int, optional): Decimal places for weight (default 3)

        Returns:
            dict: {'product_id': int, 'qty': Decimal, 'is_weighted': True}
            None: If barcode doesn't match format or validation fails

        Example:
            >>> ScaleService.parse_barcode('2012345006780')
            {'product_id': 12345, 'qty': Decimal('6.780'), 'is_weighted': True}
        """
        # Use defaults if not provided
        prefix = prefix or ScaleService.DEFAULT_PREFIX
        decimal_places = decimal_places or ScaleService.DEFAULT_DECIMAL_PLACES

        # Validate barcode length
        if not barcode or len(barcode) != 13:
            return None

        # Check if barcode starts with the expected prefix
        if not barcode.startswith(prefix):
            return None

        try:
            # Extract components
            # Format: PP IIIII WWWWW C
            product_id_str = barcode[2:7]  # 5 digits for product ID
            weight_str = barcode[7:12]  # 5 digits for weight/price

            # Validate checksum (EAN-13 algorithm)
            if not ScaleService._validate_ean13_checksum(barcode):
                return None

            # Parse product ID
            product_id = int(product_id_str)

            # Parse weight with decimal places
            weight_value = int(weight_str)
            divisor = 10**decimal_places
            quantity = Decimal(weight_value) / Decimal(divisor)

            return {"product_id": product_id, "qty": quantity, "is_weighted": True}

        except (ValueError, IndexError):
            return None

    @staticmethod
    def _validate_ean13_checksum(barcode: str) -> bool:
        """
        Validate EAN-13 checksum using the standard algorithm.

        Args:
            barcode (str): 13-digit barcode

        Returns:
            bool: True if checksum is valid
        """
        if len(barcode) != 13:
            return False

        try:
            # EAN-13 checksum algorithm
            # Sum odd positions (1st, 3rd, 5th...) and multiply by 1
            # Sum even positions (2nd, 4th, 6th...) and multiply by 3
            # Add both sums, subtract from next multiple of 10
            odd_sum = sum(int(barcode[i]) for i in range(0, 12, 2))
            even_sum = sum(int(barcode[i]) for i in range(1, 12, 2))

            total = odd_sum + (even_sum * 3)
            checksum = (10 - (total % 10)) % 10

            return checksum == int(barcode[12])

        except (ValueError, IndexError):
            return False

    @staticmethod
    def is_scale_barcode(barcode: str, prefix: Optional[str] = None) -> bool:
        """
        Check if a barcode is a scale-generated barcode.

        Args:
            barcode (str): The barcode to check
            prefix (str, optional): Expected prefix (default '20')

        Returns:
            bool: True if barcode matches scale format
        """
        prefix = prefix or ScaleService.DEFAULT_PREFIX
        return barcode is not None and len(barcode) == 13 and barcode.startswith(prefix) and barcode.isdigit()
