"""Extract transcripts from YouTube URLs using LangChain's YoutubeLoader."""
import logging
from typing import List

from langchain_community.document_loaders import YoutubeLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class YouTubeProcessor:
    """Load transcripts from a list of YouTube URLs into LangChain Documents."""

    def load(self, urls: List[str]) -> List[Document]:
        docs: List[Document] = []
        for url in urls:
            url = url.strip()
            if not url:
                continue
            try:
                loader = YoutubeLoader.from_youtube_url(
                    url,
                    add_video_info=False,
                    language=["en", "en-US", "en-GB"],
                )
                loaded = loader.load()
                if loaded:
                    docs.extend(loaded)
                    logger.info("Loaded transcript from %s (%d chunk(s))", url, len(loaded))
                else:
                    logger.warning("No transcript returned for %s", url)
            except Exception as exc:
                logger.warning("Skipping %s — could not load transcript: %s", url, exc)
        return docs
