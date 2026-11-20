"""Feature flag names, shop types, preset matrix, and implemented feature registry (#942)."""


class ShopTypes:
    """Pre-configured shop types available during first-run setup."""

    GROCERY = "grocery"
    PHARMACY = "pharmacy"
    HARDWARE = "hardware"
    CLOTHING = "clothing"
    PHONE_ELECTRONICS = "phone_electronics"
    BOOKSHOP = "bookshop"
    BAKERY = "bakery"
    OTHER = "other"

    ALL = (
        GROCERY,
        PHARMACY,
        HARDWARE,
        CLOTHING,
        PHONE_ELECTRONICS,
        BOOKSHOP,
        BAKERY,
        OTHER,
    )


class Features:
    """Constants for database-backed feature flags."""

    EXPIRY_DATES = "expiry_dates"
    BATCHES = "batches"
    WEIGHT_SCALE = "weight_scale"
    PRICE_BOARD = "price_board"
    CREDIT_BOOK = "credit_book"
    CHEQUES = "cheques"
    SERIAL_TRACKING = "serial_tracking"
    VARIANTS = "variants"
    QUOTATIONS = "quotations"
    UNIT_CONVERSION = "unit_conversion"
    DEPOSITS = "deposits"
    WARRANTY = "warranty"

    ALL = (
        EXPIRY_DATES,
        BATCHES,
        WEIGHT_SCALE,
        PRICE_BOARD,
        CREDIT_BOOK,
        CHEQUES,
        SERIAL_TRACKING,
        VARIANTS,
        QUOTATIONS,
        UNIT_CONVERSION,
        DEPOSITS,
        WARRANTY,
    )


# Features that are implemented in code and visible as toggles in Settings -> Features (#942)
IMPLEMENTED_FEATURES = {
    Features.WARRANTY,
    Features.CREDIT_BOOK,
    Features.SERIAL_TRACKING,
    Features.CHEQUES,
}

# Approved 7-shop preset matrix (Decision D34).
# optional cells are False initially but available in Settings.
PRESET_MATRIX: dict[str, dict[str, bool]] = {
    ShopTypes.GROCERY: {
        Features.EXPIRY_DATES: False,  # optional -> False initially
        Features.BATCHES: True,
        Features.WEIGHT_SCALE: True,
        Features.PRICE_BOARD: True,
        Features.CREDIT_BOOK: True,
        Features.CHEQUES: False,
        Features.SERIAL_TRACKING: False,
        Features.VARIANTS: False,
        Features.QUOTATIONS: False,
        Features.UNIT_CONVERSION: True,
        Features.DEPOSITS: False,  # optional -> False initially
        Features.WARRANTY: False,
    },
    ShopTypes.PHARMACY: {
        Features.EXPIRY_DATES: True,
        Features.BATCHES: True,
        Features.WEIGHT_SCALE: False,
        Features.PRICE_BOARD: False,
        Features.CREDIT_BOOK: True,
        Features.CHEQUES: True,
        Features.SERIAL_TRACKING: False,
        Features.VARIANTS: False,
        Features.QUOTATIONS: False,
        Features.UNIT_CONVERSION: True,
        Features.DEPOSITS: False,
        Features.WARRANTY: False,
    },
    ShopTypes.HARDWARE: {
        Features.EXPIRY_DATES: False,
        Features.BATCHES: False,
        Features.WEIGHT_SCALE: True,
        Features.PRICE_BOARD: True,
        Features.CREDIT_BOOK: True,
        Features.CHEQUES: True,
        Features.SERIAL_TRACKING: False,  # optional -> False initially
        Features.VARIANTS: False,
        Features.QUOTATIONS: True,
        Features.UNIT_CONVERSION: True,
        Features.DEPOSITS: False,
        Features.WARRANTY: False,  # optional -> False initially
    },
    ShopTypes.CLOTHING: {
        Features.EXPIRY_DATES: False,
        Features.BATCHES: False,
        Features.WEIGHT_SCALE: False,
        Features.PRICE_BOARD: False,
        Features.CREDIT_BOOK: False,
        Features.CHEQUES: False,
        Features.SERIAL_TRACKING: False,
        Features.VARIANTS: True,
        Features.QUOTATIONS: False,
        Features.UNIT_CONVERSION: False,
        Features.DEPOSITS: False,
        Features.WARRANTY: False,
    },
    ShopTypes.PHONE_ELECTRONICS: {
        Features.EXPIRY_DATES: False,
        Features.BATCHES: False,
        Features.WEIGHT_SCALE: False,
        Features.PRICE_BOARD: False,
        Features.CREDIT_BOOK: True,
        Features.CHEQUES: True,
        Features.SERIAL_TRACKING: True,
        Features.VARIANTS: False,  # optional -> False initially
        Features.QUOTATIONS: True,
        Features.UNIT_CONVERSION: False,
        Features.DEPOSITS: False,
        Features.WARRANTY: True,
    },
    ShopTypes.BOOKSHOP: {
        Features.EXPIRY_DATES: False,
        Features.BATCHES: False,
        Features.WEIGHT_SCALE: False,
        Features.PRICE_BOARD: False,
        Features.CREDIT_BOOK: True,
        Features.CHEQUES: True,
        Features.SERIAL_TRACKING: False,
        Features.VARIANTS: False,
        Features.QUOTATIONS: True,
        Features.UNIT_CONVERSION: False,
        Features.DEPOSITS: False,
        Features.WARRANTY: False,
    },
    ShopTypes.BAKERY: {
        Features.EXPIRY_DATES: True,
        Features.BATCHES: False,
        Features.WEIGHT_SCALE: True,
        Features.PRICE_BOARD: True,
        Features.CREDIT_BOOK: False,
        Features.CHEQUES: False,
        Features.SERIAL_TRACKING: False,
        Features.VARIANTS: False,
        Features.QUOTATIONS: True,
        Features.UNIT_CONVERSION: False,
        Features.DEPOSITS: False,
        Features.WARRANTY: False,
    },
    ShopTypes.OTHER: {
        Features.EXPIRY_DATES: False,
        Features.BATCHES: False,
        Features.WEIGHT_SCALE: False,
        Features.PRICE_BOARD: False,
        Features.CREDIT_BOOK: False,
        Features.CHEQUES: False,
        Features.SERIAL_TRACKING: False,
        Features.VARIANTS: False,
        Features.QUOTATIONS: False,
        Features.UNIT_CONVERSION: False,
        Features.DEPOSITS: False,
        Features.WARRANTY: False,
    },
}

# Unit definitions to seed per shop type (#942)
PRESET_UNITS: dict[str, list[tuple[str, str, int]]] = {
    # (name, abbreviation, decimal_places)
    ShopTypes.GROCERY: [
        ("Piece", "pcs", 0),
        ("Kilogram", "kg", 3),
        ("Gram", "g", 0),
        ("Pack", "pk", 0),
    ],
    ShopTypes.PHARMACY: [
        ("Piece", "pcs", 0),
        ("Tablet", "tab", 0),
        ("Capsule", "cap", 0),
        ("Bottle", "btl", 0),
    ],
    ShopTypes.HARDWARE: [
        ("Piece", "pcs", 0),
        ("Foot", "ft", 2),
        ("Meter", "m", 2),
        ("Kilogram", "kg", 3),
        ("Roll", "roll", 0),
    ],
    ShopTypes.CLOTHING: [
        ("Piece", "pcs", 0),
    ],
    ShopTypes.PHONE_ELECTRONICS: [
        ("Piece", "pcs", 0),
    ],
    ShopTypes.BOOKSHOP: [
        ("Piece", "pcs", 0),
    ],
    ShopTypes.BAKERY: [
        ("Piece", "pcs", 0),
        ("Kilogram", "kg", 3),
    ],
    ShopTypes.OTHER: [
        ("Piece", "pcs", 0),
    ],
}

# Approved minimal category matrices per shop type (Decision D34/D35)
PRESET_CATEGORIES: dict[str, list[dict[str, str]]] = {
    ShopTypes.GROCERY: [
        {"en": "Food & Provisions", "si": "ආහාර සහ ද්‍රව්‍ය", "ta": "உணவுப் பொருட்கள்", "color": "#FF9800"},
        {"en": "Beverages", "si": "බීම වර්ග", "ta": "பானங்கள்", "color": "#00BCEB"},
        {
            "en": "Snacks & Confectionery",
            "si": "කෙටි කෑම සහ රසකැවිලි",
            "ta": "சிற்றுண்டிகள் மற்றும் இனிப்புகள்",
            "color": "#FFD700",
        },
        {"en": "Household & Cleaning", "si": "ගෘහ සහ පිරිසිදුකාරක", "ta": "வீட்டுப் பராமரிப்பு பொருட்கள்", "color": "#9C27B0"},
        {"en": "Personal Care", "si": "පුද්ගලික සත්කාර", "ta": "தனிநபர் பராமரிப்பு", "color": "#E91E63"},
    ],
    ShopTypes.PHARMACY: [
        {
            "en": "Prescription Medicines",
            "si": "බෙහෙත් වට්ටෝරු ඖෂධ",
            "ta": "மருத்துவர் பரிந்துரை மருந்துகள்",
            "color": "#F44336",
        },
        {"en": "Over The Counter", "si": "සාමාන්‍ය ඖෂධ (OTC)", "ta": "பொது மருந்துகள்", "color": "#4CAF50"},
        {"en": "Wellness & Supplements", "si": "සුවතා සහ අතිරේක", "ta": "ஆரோக்கியம் மற்றும் சத்துணவு", "color": "#00BCD4"},
        {
            "en": "Medical Devices & First Aid",
            "si": "වෛද්‍ය උපකරණ සහ ප්‍රථමාධාර",
            "ta": "மருத்துவ உபகரணங்கள் மற்றும் முதலுதவி",
            "color": "#2196F3",
        },
    ],
    ShopTypes.HARDWARE: [
        {"en": "Building & Masonry", "si": "ඉදිකිරීම් ද්‍රව්‍ය", "ta": "கட்டடப் பொருட்கள்", "color": "#795548"},
        {"en": "Plumbing & Sanitary", "si": "නල සහ සනීපාරක්ෂක", "ta": "குழாய் மற்றும் சுகாதாரப் பொருட்கள்", "color": "#03A9F4"},
        {"en": "Electrical & Lighting", "si": "විදුලි සහ ආලෝකකරණ", "ta": "மின்சாரம் மற்றும் விளக்குகள்", "color": "#FFC107"},
        {"en": "Tools & Fasteners", "si": "මෙවලම් සහ ඇණ/මුරිච්චි", "ta": "கருவிகள் மற்றும் திருகுகள்", "color": "#607D8B"},
        {"en": "Paints & Solvents", "si": "තීන්ත සහ ද්‍රාවක", "ta": "வண்ணங்கள் மற்றும் கரைப்பான்கள்", "color": "#E91E63"},
    ],
    ShopTypes.CLOTHING: [
        {"en": "Men's Wear", "si": "පිරිමි ඇඳුම්", "ta": "ஆண்கள் ஆடை", "color": "#3F51B5"},
        {"en": "Women's Wear", "si": "කාන්තා ඇඳුම්", "ta": "பெண்கள் ஆடை", "color": "#E91E63"},
        {"en": "Kids' Wear", "si": "ළමා ඇඳුම්", "ta": "குழந்தைகள் ஆடை", "color": "#4CAF50"},
        {"en": "Accessories & Footwear", "si": "උපාංග සහ පාවහන්", "ta": "பாகங்கள் மற்றும் பாதணிகள்", "color": "#FF9800"},
    ],
    ShopTypes.PHONE_ELECTRONICS: [
        {"en": "Mobile Phones & Tablets", "si": "ජංගම දුරකථන සහ ටැබ්ලට්", "ta": "கையடக்கத் தொலைபேசிகள்", "color": "#2196F3"},
        {"en": "Audio & Accessories", "si": "ශ්‍රව්‍ය සහ උපාංග", "ta": "ஆடியோ மற்றும் பாகங்கள்", "color": "#9C27B0"},
        {"en": "Parts & Protection", "si": "අමතර කොටස් සහ ආරක්ෂණ", "ta": "உதிரிப்பாகங்கள் மற்றும் பாதுகாப்பு", "color": "#607D8B"},
        {"en": "Small Appliances", "si": "කුඩා විදුලි උපකරණ", "ta": "சிறிய வீட்டு உபயோகப் பொருட்கள்", "color": "#FF5722"},
    ],
    ShopTypes.BOOKSHOP: [
        {"en": "Books & Publications", "si": "පොත් සහ ප්‍රකාශන", "ta": "புத்தகங்கள் மற்றும் வெளியீடுகள்", "color": "#8D6E63"},
        {
            "en": "School & Office Stationery",
            "si": "පාසල් සහ කාර්යාල ලිපිද්‍රව්‍ය",
            "ta": "பள்ளி மற்றும் அலுவலக எழுதுபொருட்கள்",
            "color": "#009688",
        },
        {"en": "Art & Craft Supplies", "si": "චිත්‍ර සහ නිර්මාණ ද්‍රව්‍ය", "ta": "கலை மற்றும் கைவினைப் பொருட்கள்", "color": "#E91E63"},
        {"en": "Paper & Printing", "si": "කඩදාසි සහ මුද්‍රණ", "ta": "காகிதம் மற்றும் அச்சிடுதல்", "color": "#3F51B5"},
    ],
    ShopTypes.BAKERY: [
        {"en": "Bread & Buns", "si": "පාන් සහ බනිස්", "ta": "பாண் மற்றும் பன்கள்", "color": "#FF9800"},
        {"en": "Pastries & Savouries", "si": "පේස්ට්‍රි සහ සැර කෑම", "ta": "பேஸ்ட்ரிகள் மற்றும் கார வகைகள்", "color": "#FF5722"},
        {"en": "Cakes & Sweets", "si": "කේක් සහ රසකැවිලි", "ta": "கேக் மற்றும் இனிப்புகள்", "color": "#E91E63"},
        {"en": "Beverages", "si": "බීම වර්ග", "ta": "பானங்கள்", "color": "#00BCD4"},
    ],
    ShopTypes.OTHER: [],
}
