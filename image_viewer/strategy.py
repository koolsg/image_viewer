from abc import ABC, abstractmethod
from typing import Optional, Tuple
from .logger import get_logger

_logger = get_logger("strategy")


class DecodingStrategy(ABC):
    """이미지 디코딩 전략의 추상 기본 클래스."""

    @abstractmethod
    def get_target_size(self, viewport_width: int, viewport_height: int) -> Tuple[Optional[int], Optional[int]]:
        """뷰포트 크기에 따른 타겟 디코딩 크기를 반환합니다.
        
        Returns:
            (target_width, target_height) tuple. None은 원본 크기를 의미합니다.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """전략 이름(UI에 표시용)을 반환합니다."""
        pass

    @abstractmethod
    def supports_hq_downscale(self) -> bool:
        """고품질 다운스케일 옵션을 지원하는지 반환합니다."""
        pass


class ThumbnailStrategy(DecodingStrategy):
    """빠른 뷰잉을 위한 썸네일 전략: 화면 크기 기준 디코딩."""

    def __init__(self):
        self.name = "썸네일"
        _logger.debug("ThumbnailStrategy initialized")

    def get_target_size(self, viewport_width: int, viewport_height: int) -> Tuple[Optional[int], Optional[int]]:
        """뷰포트 크기에 맞춰 디코딩합니다."""
        if viewport_width <= 0 or viewport_height <= 0:
            return None, None
        _logger.debug("ThumbnailStrategy: target size = (%d, %d)", viewport_width, viewport_height)
        return viewport_width, viewport_height

    def get_name(self) -> str:
        return self.name

    def supports_hq_downscale(self) -> bool:
        """썸네일 모드에서는 HQ 다운스케일이 의미 없습니다."""
        return False


class FullStrategy(DecodingStrategy):
    """원본 해상도 기반 전략: 최고 품질."""

    def __init__(self):
        self.name = "원본"
        _logger.debug("FullStrategy initialized")

    def get_target_size(self, viewport_width: int, viewport_height: int) -> Tuple[Optional[int], Optional[int]]:
        """원본 크기로 디코딩합니다."""
        _logger.debug("FullStrategy: decoding at full resolution")
        return None, None

    def get_name(self) -> str:
        return self.name

    def supports_hq_downscale(self) -> bool:
        """원본 모드에서는 HQ 다운스케일을 지원합니다."""
        return True
