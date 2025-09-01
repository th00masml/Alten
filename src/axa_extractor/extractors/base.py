from abc import ABC, abstractmethod
from typing import Optional
from ..fields import ExtractionResult


class BaseExtractor(ABC):
    name: str = "base"

    @abstractmethod
    def can_process(self, file_bytes: bytes) -> bool:
        ...

    @abstractmethod
    def extract(self, file_bytes: bytes, config: Optional[dict] = None) -> ExtractionResult:
        ...

