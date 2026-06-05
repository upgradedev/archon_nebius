from abc import ABC, abstractmethod
from pathlib import Path
from models.document import ExtractedDocument


class BaseExtractor(ABC):
    """All extractors return a normalised ExtractedDocument."""

    @abstractmethod
    def can_handle(self, path: Path) -> bool:
        ...

    @abstractmethod
    def extract(self, path: Path) -> ExtractedDocument:
        ...
