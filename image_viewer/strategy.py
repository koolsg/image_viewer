from abc import ABC, abstractmethod

from .logger import get_logger

_logger = get_logger("strategy")


class DecodingStrategy(ABC):


    """Abstract base class for image decoding strategies."""





    @abstractmethod


    def get_target_size(self, viewport_width: int, viewport_height: int) -> tuple[int | None, int | None]:


        """Returns the target decoding size based on the viewport size.





        Returns:


            (target_width, target_height) tuple. None means original size.


        """


        pass





    @abstractmethod


    def get_name(self) -> str:


        """Returns the strategy name (for UI display)."""


        pass





    @abstractmethod


    def supports_hq_downscale(self) -> bool:


        """Returns whether high-quality downscaling is supported."""


        pass








class FastViewStrategy(DecodingStrategy):


    """Fast view mode: calculates target resolution based on viewport size."""





    def __init__(self):


        self.name = "fast view"


        _logger.debug("FastViewStrategy initialized")





    def get_target_size(self, viewport_width: int, viewport_height: int) -> tuple[int | None, int | None]:


        """Calculate the resolution to use based on the viewport area."""


        if viewport_width <= 0 or viewport_height <= 0:


            return None, None


        _logger.debug("FastViewStrategy: target size = (%d, %d)", viewport_width, viewport_height)


        return viewport_width, viewport_height





    def get_name(self) -> str:


        return self.name





    def supports_hq_downscale(self) -> bool:


        return False











class FullStrategy(DecodingStrategy):


    """Original resolution-based strategy: highest quality."""





    def __init__(self):


        self.name = "original"


        _logger.debug("FullStrategy initialized")





    def get_target_size(self, viewport_width: int, viewport_height: int) -> tuple[int | None, int | None]:


        """Decodes at the original size."""


        _logger.debug("FullStrategy: decoding at full resolution")


        return None, None





    def get_name(self) -> str:


        return self.name





    def supports_hq_downscale(self) -> bool:


        """HQ downscaling is supported in original mode."""


        return True

