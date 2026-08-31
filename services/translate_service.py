"""
Translation service for ,translate.

Language detection is done LOCALLY (langdetect package, no API call)
since MyMemory's real HTTP API requires an explicit source language
in its `langpair` parameter - there is no "auto" value it accepts
server-side, despite some wrapper libraries advertising "auto"
support (they do their own separate detection step first, same as
here). Translation itself uses api.mymemory.translated.net, a free,
no-signup-required API.
"""

from __future__ import annotations

import aiohttp

LANGUAGE_NAMES = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic",
    "hy": "Armenian", "az": "Azerbaijani", "eu": "Basque", "be": "Belarusian",
    "bn": "Bengali", "bs": "Bosnian", "bg": "Bulgarian", "ca": "Catalan",
    "ceb": "Cebuano", "zh-cn": "Chinese (Simplified)", "zh-tw": "Chinese (Traditional)",
    "co": "Corsican", "hr": "Croatian", "cs": "Czech", "da": "Danish",
    "nl": "Dutch", "en": "English", "eo": "Esperanto", "et": "Estonian",
    "fi": "Finnish", "fr": "French", "fy": "Frisian", "gl": "Galician",
    "ka": "Georgian", "de": "German", "el": "Greek", "gu": "Gujarati",
    "ht": "Haitian Creole", "ha": "Hausa", "haw": "Hawaiian", "he": "Hebrew",
    "hi": "Hindi", "hmn": "Hmong", "hu": "Hungarian", "is": "Icelandic",
    "ig": "Igbo", "id": "Indonesian", "ga": "Irish", "it": "Italian",
    "ja": "Japanese", "jw": "Javanese", "kn": "Kannada", "kk": "Kazakh",
    "km": "Khmer", "ko": "Korean", "ku": "Kurdish", "ky": "Kyrgyz",
    "lo": "Lao", "la": "Latin", "lv": "Latvian", "lt": "Lithuanian",
    "lb": "Luxembourgish", "mk": "Macedonian", "mg": "Malagasy", "ms": "Malay",
    "ml": "Malayalam", "mt": "Maltese", "mi": "Maori", "mr": "Marathi",
    "mn": "Mongolian", "my": "Myanmar (Burmese)", "ne": "Nepali", "no": "Norwegian",
    "ny": "Nyanja (Chichewa)", "ps": "Pashto", "fa": "Persian", "pl": "Polish",
    "pt": "Portuguese", "pa": "Punjabi", "ro": "Romanian", "ru": "Russian",
    "sm": "Samoan", "gd": "Scots Gaelic", "sr": "Serbian", "st": "Sesotho",
    "sn": "Shona", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "so": "Somali", "es": "Spanish", "su": "Sundanese",
    "sw": "Swahili", "sv": "Swedish", "tl": "Tagalog (Filipino)", "tg": "Tajik",
    "ta": "Tamil", "te": "Telugu", "th": "Thai", "tr": "Turkish",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese",
    "cy": "Welsh", "xh": "Xhosa", "yi": "Yiddish", "yo": "Yoruba", "zu": "Zulu",
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code.lower(), code.upper())


def detect_language(text: str) -> str | None:
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return None


async def translate(text: str, target: str = "en") -> tuple[str, str] | None:
    """Returns (translated_text, source_language_code), or None if
    detection/translation failed."""
    source = detect_language(text)
    if source is None:
        return None

    if source == target:
        return None  # already in the target language - nothing to do

    params = {"q": text[:500], "langpair": f"{source}|{target}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.mymemory.translated.net/get", params=params,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None

    translated = data.get("responseData", {}).get("translatedText")
    if not translated:
        return None

    return translated, source