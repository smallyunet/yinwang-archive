import argparse
import json
import os
import re
from collections import Counter, defaultdict
MIN_YEAR = "2010"
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MissingGroup:
    base_name: str
    files: list[str]
    any_valid: bool
    invalid_reasons: Counter


def get_base_name_and_version(filename: str) -> tuple[str, str]:
    match = re.search(r"^(.*)_(\d{8})\.html$", filename)
    if match:
        return match.group(1), match.group(2)
    return filename, "00000000"


def is_archive_year_allowed(version_date: str) -> bool:
    if not version_date or len(version_date) < 4:
        return True
    return version_date[:4] >= MIN_YEAR


def is_valid_content(content: str) -> bool:
    if not content:
        return False

    s = content.lower()

    # Known junk title/patterns from domain parking
    if "surely i am joking" in s:
        return False

    # Empty app shell
    if '<div id="app"></div>' in s and len(s) < 2000:
        return False

    # Too short (but allow redirect/moved pages)
    if len(s) < 200 and "redirect" not in s and "moved" not in s:
        return False

    return True


def invalid_reason(content: str) -> str:
    if not content:
        return "empty"

    s = content.lower()

    if "surely i am joking" in s:
        return "junk-domain-parking"

    if '<div id="app"></div>' in s and len(s) < 2000:
        return "empty-app-shell"

    if len(s) < 200 and "redirect" not in s and "moved" not in s:
        return "too-short"

    return "other"


def extract_index_article_hrefs(index_html: str) -> list[str]:
    # generate_site.py uses single quotes around href
    return re.findall(r"href='(blog-cn[^']+?\.html)'", index_html)


def build_report(archives_dir: str, docs_dir: str) -> dict[str, Any]:
    index_path = os.path.join(docs_dir, "index.html")

    archive_files = []
    for f in os.listdir(archives_dir):
        if not (f.startswith("blog-cn") and f.endswith(".html")):
            continue
        _base, version_date = get_base_name_and_version(f)
        if not is_archive_year_allowed(version_date):
            continue
        archive_files.append(f)

    archive_groups: dict[str, list[str]] = defaultdict(list)
    for filename in archive_files:
        base_name, _version = get_base_name_and_version(filename)
        archive_groups[base_name].append(filename)

    with open(index_path, "r", encoding="utf-8", errors="ignore") as f:
        index_html = f.read()

    hrefs = extract_index_article_hrefs(index_html)
    index_bases = {get_base_name_and_version(href)[0] for href in hrefs}

    archive_bases = set(archive_groups.keys())
    missing_bases = sorted(archive_bases - index_bases)

    missing_groups: list[MissingGroup] = []

    for base in missing_bases:
        files = sorted(archive_groups[base])
        reasons: Counter = Counter()
        any_valid = False

        for fn in files:
            path = os.path.join(archives_dir, fn)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            ok = is_valid_content(content)
            any_valid = any_valid or ok
            if not ok:
                reasons[invalid_reason(content)] += 1

        missing_groups.append(
            MissingGroup(
                base_name=base,
                files=files,
                any_valid=any_valid,
                invalid_reasons=reasons,
            )
        )

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "archives_dir": archives_dir,
        "docs_dir": docs_dir,
        "index_path": index_path,
        "archives_blog_cn_versions": len(archive_files),
        "archives_blog_cn_distinct_articles": len(archive_bases),
        "index_listed_articles": len(index_bases),
        "missing_distinct_articles": len(missing_groups),
        "missing_breakdown": dict(Counter("has-valid-but-missing" if g.any_valid else "all-invalid" for g in missing_groups)),
        "missing_examples": [
            {
                "base_name": g.base_name,
                "any_valid": g.any_valid,
                "invalid_reasons": dict(g.invalid_reasons),
                "files": g.files,
            }
            for g in missing_groups
        ],
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Check docs/index.html coverage against archives/*.html")
    parser.add_argument("--archives-dir", default="archives")
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--json", dest="json_path", default="", help="Write full report JSON to this path")
    parser.add_argument("--max-examples", type=int, default=20)

    args = parser.parse_args()

    report = build_report(args.archives_dir, args.docs_dir)

    print("archives blog-cn versions:", report["archives_blog_cn_versions"])
    print("archives blog-cn distinct articles:", report["archives_blog_cn_distinct_articles"])
    print("index listed articles:", report["index_listed_articles"])
    print("missing distinct articles:", report["missing_distinct_articles"])
    print("missing breakdown:", report["missing_breakdown"])

    examples = report["missing_examples"][: args.max_examples]
    if examples:
        print("\nexamples:")
        for ex in examples:
            reasons = ex.get("invalid_reasons") or {}
            print("-", ex["base_name"], "any_valid=" + str(ex["any_valid"]), reasons)

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("\nwrote:", args.json_path)


if __name__ == "__main__":
    main()
