import fnmatch
import re


def normalize_match_patterns(patterns) -> list[str]:
    if isinstance(patterns, str):
        patterns = re.split(r"[\n,]+", patterns)
    result = []
    for pattern in patterns or []:
        pattern = str(pattern or "").strip().lower()
        if pattern and pattern not in result:
            result.append(pattern)
    return result


def normalize_aliases(aliases) -> list[str]:
    if isinstance(aliases, str):
        aliases = re.split(r"[\n,]+", aliases)
    result = []
    for alias in aliases or []:
        alias = str(alias or "").strip().lower()
        if alias and "@" in alias and alias not in result:
            result.append(alias)
    return result


def pattern_matches_address(pattern: str, addr: str) -> bool:
    addr = (addr or "").lower()
    pattern = (pattern or "").lower()
    if not addr or "@" not in addr or not pattern:
        return False
    domain = addr.split("@", 1)[1]
    if "@" in pattern:
        return fnmatch.fnmatch(addr, pattern)
    return fnmatch.fnmatch(domain, pattern.lstrip("@"))

