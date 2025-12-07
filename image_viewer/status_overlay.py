from .image_engine.strategy import FastViewStrategy
from .logger import get_logger

_logger = get_logger("status_overlay")


class StatusOverlayBuilder:
    def __init__(self, viewer):
        self.viewer = viewer

    def build_parts(self) -> list[str]:
        parts: list[str] = []

        try:
            parts.append(f"[{self.viewer.decoding_strategy.get_name()}]")
        except Exception as e:
            _logger.debug("failed to get strategy name: %s", e)

        file_resolution = self._get_file_resolution()
        output_resolution = self._get_output_resolution()

        if file_resolution:
            parts.append(f"File {file_resolution[0]}x{file_resolution[1]}")

        if output_resolution:
            parts.append(f"Output {output_resolution[0]}x{output_resolution[1]}")
            scale = self.viewer._calculate_scale(
                output_resolution[0], output_resolution[1]
            )
        else:
            scale = self.viewer._calculate_scale(
                file_resolution[0] if file_resolution else None,
                file_resolution[1] if file_resolution else None,
            )

        if scale is not None:
            parts.append(f"@ {scale:.2f}x")

        return parts

    def _get_file_resolution(self) -> tuple[int, int] | None:
        if not self.viewer.image_files or self.viewer.current_index < 0:
            return None
        path = self.viewer.image_files[self.viewer.current_index]
        width, height = self.viewer._get_file_dimensions(path)
        if width and height:
            return width, height
        return None

    def _get_output_resolution(self) -> tuple[int, int] | None:
        if isinstance(self.viewer.decoding_strategy, FastViewStrategy):
            dec_w, dec_h = self.viewer._get_decoded_dimensions()
            if dec_w and dec_h:
                return dec_w, dec_h

        file_res = self._get_file_resolution()
        if file_res:
            return file_res

        return self.viewer._get_decoded_dimensions()
