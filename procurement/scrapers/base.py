"""Abstract base class for procurement site scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from models.rfq import RFQ


class BaseScraper(ABC):
    """All scrapers implement this interface so new sources can be added easily."""

    name: str = "base"

    @abstractmethod
    def scrape(self) -> list[RFQ]:
        """Scrape the source and return a list of raw RFQ objects.

        Implementations should handle authentication, pagination, and
        downloading of attachment files.  Relevance filtering is done
        downstream by the parser.
        """
        ...
