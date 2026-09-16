import hashlib
import platform


class LicenseService:
    @staticmethod
    def get_machine_id() -> str:
        """Generate a unique machine ID based on hardware."""
        node = platform.node()
        system = platform.system()
        machine = platform.machine()
        processor = platform.processor()

        raw_id = f"{node}-{system}-{machine}-{processor}"
        return hashlib.sha256(raw_id.encode()).hexdigest()

    @staticmethod
    def validate_license() -> bool:
        """
        Check if a valid license exists.
        For now, this is a stub that always returns False (Trial Mode).
        """
        # Stub: always returns False (Trial Mode) until license system is built
        return False

    @staticmethod
    def get_license_status() -> str:
        if LicenseService.validate_license():
            return "Licensed"
        else:
            return "Trial Mode"
