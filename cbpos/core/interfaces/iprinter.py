from abc import ABC, abstractmethod


class IPrinter(ABC):
    """
    Abstract Interface for POS Printers.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the printer."""

    @abstractmethod
    def disconnect(self):
        """Disconnect from the printer."""

    @abstractmethod
    def print_text(self, text: str):
        """Print raw text."""

    @abstractmethod
    def print_line(self, text: str):
        """Print text followed by a newline."""

    @abstractmethod
    def cut(self):
        """Cut the paper."""

    @abstractmethod
    def kick_drawer(self):
        """Open the cash drawer."""
