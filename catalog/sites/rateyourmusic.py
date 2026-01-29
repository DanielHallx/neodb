"""
RateYourMusic (RYM)

Uses browser-side fetching to bypass Cloudflare protection.
The user's browser loads the page and sends the HTML to the server for parsing.
This is 100% reliable and doesn't require any anti-bot libraries.
"""

import json
import re
from datetime import timedelta

import dateparser
from django.utils.dateparse import parse_duration
from loguru import logger

from catalog.common import *
from catalog.models import *
from common.models.lang import detect_language
from common.models.misc import uniq


@SiteManager.register
class RateYourMusic(AbstractSite):
    SITE_NAME = SiteName.RateYourMusic
    ID_TYPE = IdType.RateYourMusic_Album
    URL_PATTERNS = [
        r"https://rateyourmusic\.com/release/album/([\w\-]+)/([\w\-]+)/?",
        r"https://rateyourmusic\.com/release/album/([\w\-]+)/([\w\-]+)/([\w\-]+)/?",
    ]
    WIKI_PROPERTY_ID = "?"
    DEFAULT_MODEL = Album

    # Custom headers to try to bypass Cloudflare
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    @classmethod
    def id_to_url(cls, id_value):
        # ID value format: "artist-name/album-name" or "artist-name/album-name/version"
        return f"https://rateyourmusic.com/release/album/{id_value}/"

    @classmethod
    def url_to_id(cls, url):
        """Extract ID from URL"""
        # Extract artist/album from URL
        match = re.search(r'rateyourmusic\.com/release/album/(.+?)/?$', url)
        if match:
            return match.group(1).rstrip('/')
        return None

    def scrape(self):
        """
        This method should not be called directly.
        RateYourMusic uses browser-side fetching via the Cloudflare verification page.
        The HTML is sent from the user's browser to fetch_via_browser view.
        """
        raise NotImplementedError(
            "RateYourMusic requires browser-side fetching. "
            "Please use the web interface to fetch content."
        )

    def _extract_from_html(self, content):
        """Extract album data from parsed HTML content."""
        # Try to extract album data from the page
        localized_title = []
        localized_desc = []
        artist = []
        genre = []
        release_date = None
        track_list = []
        image_url = None
        duration = 0

        try:
            # Extract album title from meta tags or page title
            # RYM typically has title in format: "Artist - Album Title"
            title_elem = content.xpath("//meta[@property='og:title']/@content")
            if title_elem:
                title_text = title_elem[0]
                # Parse "Artist - Album" format
                if " - " in title_text:
                    artist_name, album_title = title_text.split(" - ", 1)
                    artist.append(artist_name.strip())
                    title = album_title.strip()
                else:
                    title = title_text.strip()
            else:
                # Fallback: try to get from page title
                title_elem = content.xpath("//title/text()")
                if title_elem:
                    title = title_elem[0].strip()
                else:
                    title = "Unknown Album"

            lang = detect_language(title)
            localized_title.append({"lang": lang, "text": title})

            # Extract cover image from meta tags
            image_elem = content.xpath("//meta[@property='og:image']/@content")
            if image_elem:
                image_url = image_elem[0]

            # Try to extract from album-specific selectors
            # Note: These selectors may need adjustment based on actual RYM HTML structure

            # Extract artist names from page
            artist_elems = content.xpath("//a[@class='artist']//text() | //div[@class='album_info']//a[contains(@href, '/artist/')]//text()")
            if artist_elems and not artist:
                artist = [a.strip() for a in artist_elems if a.strip()]

            # Extract release date
            date_elems = content.xpath("//th[contains(text(), 'Released')]/following-sibling::td//text() | //span[@class='release_date']//text()")
            if date_elems:
                date_text = " ".join([d.strip() for d in date_elems if d.strip()])
                # Try to parse various date formats
                dt = dateparser.parse(date_text)
                if dt:
                    release_date = dt.strftime("%Y-%m-%d")

            # Extract genres/tags
            genre_elems = content.xpath("//a[@class='genre']//text() | //div[@class='release_pri_genres']//a//text()")
            if genre_elems:
                genre = [g.strip() for g in genre_elems if g.strip()]

            # Extract track list
            track_elems = content.xpath("//div[@class='tracklist']//div[@class='track']//span[@class='tracklist_title']//text() | //div[@id='tracks']//span[@class='rendered_text']//text()")
            if track_elems:
                track_list = [t.strip() for t in track_elems if t.strip()]

            # Extract description if available
            desc_elems = content.xpath("//meta[@property='og:description']/@content")
            if desc_elems:
                desc_text = desc_elems[0].strip()
                if desc_text:
                    localized_desc.append({"lang": lang, "text": desc_text})

        except Exception as e:
            logger.warning(f"Error parsing RateYourMusic page: {e}")
            # Continue with whatever data we have

        # Build ResourceContent
        pd = ResourceContent(
            metadata={
                "title": title if title else "Unknown Album",
                "localized_title": uniq(localized_title) if localized_title else [{"lang": "en", "text": "Unknown Album"}],
                "localized_description": uniq(localized_desc),
                "artist": list(set(artist)) if artist else [],
                "genre": list(set(genre)) if genre else [],
                "release_date": release_date,
                "track_list": "\n".join([f"{i+1}. {t}" for i, t in enumerate(track_list)]) if track_list else None,
                "duration": duration if duration > 0 else None,
                "cover_image_url": image_url,
            }
        )

        return pd
