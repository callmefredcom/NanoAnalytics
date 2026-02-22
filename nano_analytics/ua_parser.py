import re

# Check tablet before mobile — many tablet UAs also contain "Android" / "Mobi"
_TABLET = re.compile(r"(iPad|Tablet|PlayBook|Silk)", re.IGNORECASE)
# Android tablets omit "Mobile" from their UA; Android phones include it
_ANDROID_TABLET = re.compile(r"Android(?!.*Mobile)", re.IGNORECASE)
_MOBILE = re.compile(r"(Mobi|Android|iPhone|iPod|BlackBerry|IEMobile|Opera Mini)", re.IGNORECASE)

# Browser detection — order matters (Edge/OPR before Chrome; Samsung before Android)
_EDGE     = re.compile(r"Edg[e/]",            re.IGNORECASE)
_OPERA    = re.compile(r"(OPR|Opera)",         re.IGNORECASE)
_SAMSUNG  = re.compile(r"SamsungBrowser",      re.IGNORECASE)
_FIREFOX  = re.compile(r"Firefox",             re.IGNORECASE)
_CHROME   = re.compile(r"Chrome",              re.IGNORECASE)
_SAFARI   = re.compile(r"Safari",              re.IGNORECASE)

# OS detection
_IOS     = re.compile(r"(iPhone|iPad|iPod)",   re.IGNORECASE)
_ANDROID = re.compile(r"Android",              re.IGNORECASE)
_WINDOWS = re.compile(r"Windows",              re.IGNORECASE)
_MACOS   = re.compile(r"(Macintosh|Mac OS X)", re.IGNORECASE)
_LINUX   = re.compile(r"Linux",                re.IGNORECASE)


def device_type(ua: str | None) -> str:
    if not ua:
        return "unknown"
    if _TABLET.search(ua) or _ANDROID_TABLET.search(ua):
        return "tablet"
    if _MOBILE.search(ua):
        return "mobile"
    return "desktop"


def browser_name(ua: str | None) -> str:
    if not ua:
        return "other"
    if _EDGE.search(ua):
        return "edge"
    if _OPERA.search(ua):
        return "opera"
    if _SAMSUNG.search(ua):
        return "samsung"
    if _FIREFOX.search(ua):
        return "firefox"
    if _CHROME.search(ua):
        return "chrome"
    if _SAFARI.search(ua):
        return "safari"
    return "other"


def os_name(ua: str | None) -> str:
    if not ua:
        return "other"
    if _IOS.search(ua):
        return "ios"
    if _ANDROID.search(ua):
        return "android"
    if _WINDOWS.search(ua):
        return "windows"
    if _MACOS.search(ua):
        return "macos"
    if _LINUX.search(ua):
        return "linux"
    return "other"
