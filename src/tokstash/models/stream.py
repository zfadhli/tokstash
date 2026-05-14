"""Stream information model for TikTok livestreams."""

from typing import Optional

from pydantic import BaseModel


class StreamInfo(BaseModel):
    """Information about an active TikTok livestream.

    Attributes:
        room_id: The TikTok room identifier string.
        flv_hd: URL for the high-definition FLV stream.
        flv_ld: URL for the low-definition FLV stream.
        hls_hd: URL for the high-definition HLS playlist.
        hls_ld: URL for the low-definition HLS playlist.
    """

    room_id: str
    flv_hd: Optional[str] = None
    flv_ld: Optional[str] = None
    hls_hd: Optional[str] = None
    hls_ld: Optional[str] = None

    def best_url(self) -> str | None:
        """Pick the best available stream URL.

        Priority order: FLV HD → FLV LD → HLS HD → HLS LD.

        Returns:
            The highest-priority stream URL, or None if none are available.
        """
        return self.flv_hd or self.flv_ld or self.hls_hd or self.hls_ld
