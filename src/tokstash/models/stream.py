"""Stream information model for TikTok livestreams."""

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
    flv_hd: str | None = None
    flv_ld: str | None = None
    hls_hd: str | None = None
    hls_ld: str | None = None

    def best_url(self) -> str | None:
        """Pick the best available stream URL.

        Priority order: FLV HD → FLV LD → HLS HD → HLS LD.

        Returns:
            The highest-priority stream URL, or None if none are available.
        """
        return self.flv_hd or self.flv_ld or self.hls_hd or self.hls_ld
