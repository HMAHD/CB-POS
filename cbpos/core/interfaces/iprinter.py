from abc import ABC, abstractmethod


class IPrinter(ABC):
    """
    Abstract Interface for POS Printers.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the printer."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the printer."""
        pass

    @abstractmethod
    def print_text(self, text: str):
        """Print raw text."""
        pass

    @abstractmethod
    def print_line(self, text: str):
        """Print text followed by a newline."""
        pass

    @abstractmethod
    def cut(self):
        """Cut the paper."""
        pass

    @abstractmethod
    def kick_drawer(self):
        """Open the cash drawer."""
        pass
