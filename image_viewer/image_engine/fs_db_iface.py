from abc import ABC, abstractmethod


class IDBLoader(ABC):
    """FSModel이 의존할 DB/스캔 로더 인터페이스(스켈레톤).

    실제 구현은 Qt QObject 기반 시그널을 제공해야 함.
    """

    @abstractmethod
    def start(self, folder_path: str, generation: int) -> None:
        """스캔 시작"""
        raise NotImplementedError()

    @abstractmethod
    def stop(self) -> None:
        """스캔 중단"""
        raise NotImplementedError()

    # Expected signals by convention (documented, not enforced here):
    # - chunk_loaded(list[dict])
    # - missing_paths(list[str])
    # - finished(int)
    # - error(dict)
