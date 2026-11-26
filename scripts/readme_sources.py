"""Regenerate the data-source table in README.md (between the sources markers) from web/data/sources.json.

    uv run python scripts/readme_sources.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- sources:start -->", "<!-- sources:end -->"


def cell(text: str) -> str:
    return str(text or "").replace("|", "／").replace("\n", " ").strip()


def main() -> None:
    sources = json.loads((ROOT / "web/data/sources.json").read_text(encoding="utf-8"))
    rows = [f"共 {len(sources)} 個資料源。", "", "| 資料 | 發布機關 | 用在 |", "|---|---|---|"]
    for s in sources:
        title = f"[{cell(s['title'])}]({s['homepage']})" if s.get("homepage") else cell(s["title"])
        rows.append(f"| {title} | {cell(s.get('publisher'))} | {cell('、'.join(s.get('used_for') or []))} |")
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    readme.write_text(head + START + "\n" + "\n".join(rows) + "\n" + END + tail, encoding="utf-8")
    print(f"README.md: {len(sources)} sources")


if __name__ == "__main__":
    main()
