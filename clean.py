# clean.py
# Normalizes perfumes.json (export.py output of perfumes.sqlite) into perfumes_clean.json.
# Usage:
#   python3 clean.py [--in perfumes.json] [--out perfumes_clean.json] [--report] [--keep-unnamed]
import argparse
import hashlib
import json
import re

WS = re.compile(r"\s+")

# Longevity vote labels as stored by perfumes_scraper.py (underscores are stripped before lookup)
LON_KEYS = {
    "very long lasting": "very long lasting",
    "verylonglasting": "very long lasting",
    "long lasting": "long lasting",
    "longlasting": "long lasting",
    "moderate": "moderate",
    "weak": "weak",
    "poor": "poor",
}

BRAND_ALIASES = {
    "18 21 man made": "18.21 Man Made",
    # add more alias fixes as needed
}

# Accepted aliases for each note bucket, in priority order. The scraper emits
# {"top","middle","base"}, or {"general": [...]} for pages without a pyramid.
NOTE_BUCKETS = (
    ("top", ("top", "head")),
    ("middle", ("middle", "heart", "general")),
    ("base", ("base", "drydown")),
)


# ---------- small utils ----------
def _canon_spaces(s: str) -> str:
    return WS.sub(" ", s).strip()


def _titleish(s: str) -> str:
    """Capitalize like a title but keep small words lowercase (except the first word)."""
    if not s:
        return s
    small = {"de", "du", "des", "and", "of", "the", "a", "an", "pour", "eau"}
    parts = re.split(r'(\s+|-|/)', s.strip())
    out = []
    first = True
    for p in parts:
        if not p.strip() or p in ("-", "/"):
            out.append(p)  # separators pass through untouched
            continue
        low = p.lower()
        out.append(low if (low in small and not first) else (p[:1].upper() + p[1:]))
        first = False
    return "".join(out)


def _to_int(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s.isdigit():
        return int(s)
    try:
        f = float(s)
        if f.is_integer():
            return int(f)
    except (ValueError, OverflowError):
        pass
    return None


def _json_or_dict(v):
    """A dict, or the dict encoded in a JSON string; {} for anything else (incl. 'null')."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            parsed = json.loads(v)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _perfume_info(p) -> dict:
    """
    The scraper stores 'perfume' as {"title": ..., "image": ...}; in perfumes.json exported
    from SQLite it is a JSON string. Return that dict, or {}.
    """
    v = p.get("perfume")
    return v if isinstance(v, dict) else _json_or_dict(v)


def _normalize_counts(d: dict, key_map: dict) -> dict:
    """Normalize longevity dict keys and coerce counts to ints."""
    out = {}
    for k, v in (d or {}).items():
        lk = str(k).strip().lower()
        nk = key_map.get(lk) or key_map.get(lk.replace("_", ""))
        if not nk:
            continue
        num = _to_int(v)
        out[nk] = 0 if num is None else num
    return out


def _clean_list(items):
    """Deduplicate and nice-case a list of strings."""
    seen, out = set(), []
    for x in items or []:
        name = _titleish(_canon_spaces(str(x)))
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            out.append(name)
    return out


# ---------- parsing fields ----------
def _parse_notes(raw):
    """Return {"top": [...], "middle": [...], "base": [...]} from a notes dict or its JSON text."""
    if isinstance(raw, str):
        raw = _json_or_dict(raw)  # the scraper stores missing notes as the text 'null'
    notes = {"top": [], "middle": [], "base": []}
    if not isinstance(raw, dict):
        return notes
    # normalize keys: older scraper output contained "top " (trailing space)
    raw = {str(k).strip().lower(): v for k, v in raw.items()}
    for bucket, aliases in NOTE_BUCKETS:
        values = next((raw[a] for a in aliases if raw.get(a)), [])
        notes[bucket] = _clean_list(values if isinstance(values, list) else [])
    return notes


def _parse_main_accords(raw):
    """Return a cleaned accord list from a list or its JSON text ('null' -> [])."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return _clean_list(raw) if isinstance(raw, list) else []


def _best_name(p):
    title = _perfume_info(p).get("title")
    return _titleish(_canon_spaces(title)) if isinstance(title, str) else ""


def _best_brand(p):
    brand = _canon_spaces(str(p.get("brand") or ""))
    return BRAND_ALIASES.get(brand.lower()) or _titleish(brand)


def _best_image(p):
    image = _perfume_info(p).get("image")
    if isinstance(image, str) and image.strip():
        return image.strip()
    return None


def _slugify(brand, name):
    base = f"{brand} {name}".strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return s or "perfume"


def _stable_id(brand, name, year, dup=0):
    raw = f"{brand}::{name}::{year or ''}"
    if dup:
        raw += f"::{dup}"  # only for genuinely repeated brand/name/year rows
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------- main clean ----------
def clean(input_file="perfumes.json", output_file="perfumes_clean.json", report=False, keep_unnamed=False):
    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)
    final = []
    seen_ids, seen_slugs = set(), set()

    for p in data:
        name = _best_name(p)
        # Fragrantica has a few placeholder pages with no title; they are useless in the app.
        if not name and not keep_unnamed:
            continue

        brand = _best_brand(p)
        year = _to_int(p.get("launch_year"))
        notes = _parse_notes(p.get("notes"))
        main_accords = _parse_main_accords(p.get("main_accords"))
        longevity = _normalize_counts(_json_or_dict(p.get("longevity")), LON_KEYS)

        # build_app_db.py needs unique ids and slugs; disambiguate repeated rows deterministically
        dup = 0
        pid = _stable_id(brand, name, year)
        while pid in seen_ids:
            dup += 1
            pid = _stable_id(brand, name, year, dup)
        seen_ids.add(pid)
        slug = _slugify(brand, name)
        if slug in seen_slugs:
            slug = f"{slug}-{pid[:6]}"
        seen_slugs.add(slug)

        final.append({
            "id": pid,
            "slug": slug,
            "name": name,
            "brand": brand,
            "year": year,
            "image": _best_image(p),
            "main_accords": main_accords,
            "notes": notes,                 # {top, middle, base}
            "longevity": longevity,         # dict of vote counts
            "popularity": sum(longevity.values()),
        })

    # write the canonical, sillage-free JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)

    if report:
        total = len(final)
        with_year = sum(1 for x in final if x["year"] is not None)
        empty_name = sum(1 for x in final if not x["name"])
        avg_notes = (
            sum(len(x["notes"]["top"]) + len(x["notes"]["middle"]) + len(x["notes"]["base"]) for x in final) / total
        ) if total else 0
        print("— REPORT —")
        print(f"Total: {total}")
        print(f"With year: {with_year} ({with_year * 100 // max(total, 1)}%)")
        print(f"Empty names: {empty_name}")
        print(f"Avg notes per perfume: {avg_notes:.2f}")

    print(f"✅ Wrote {output_file} (no sillage)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="perfumes.json")
    ap.add_argument("--out", dest="out", default="perfumes_clean.json")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--keep-unnamed", action="store_true", help="keep perfumes whose page has no title")
    args = ap.parse_args()
    clean(args.inp, args.out, report=args.report, keep_unnamed=args.keep_unnamed)


if __name__ == "__main__":
    main()
