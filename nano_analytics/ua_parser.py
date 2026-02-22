import re

# Check tablet before mobile — many tablet UAs also contain "Android" / "Mobi"
_TABLET = re.compile(r"(iPad|Tablet|PlayBook|Silk)", re.IGNORECASE)
# Android tablets omit "Mobile" from their UA; Android phones include it
_ANDROID_TABLET = re.compile(r"Android(?!.*Mobile)", re.IGNORECASE)
_MOBILE = re.compile(r"(Mobi|Android|iPhone|iPod|BlackBerry|IEMobile|Opera Mini)", re.IGNORECASE)


def device_type(ua: str | None) -> str:
    if not ua:
        return "unknown"
    if _TABLET.search(ua) or _ANDROID_TABLET.search(ua):
        return "tablet"
    if _MOBILE.search(ua):
        return "mobile"
    return "desktop"
