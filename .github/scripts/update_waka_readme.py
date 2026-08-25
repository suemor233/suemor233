#!/usr/bin/env python3

"""Update the compact WakaTime section in the profile README."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


START_MARKER = "<!--START_SECTION:waka-->"
END_MARKER = "<!--END_SECTION:waka-->"
BLOCKS = "░▒▓█"
GRAPH_LENGTH = 25
TIME_COLUMN_WIDTH = 22


def make_graph(percent: float) -> str:
    markers = len(BLOCKS) - 1
    proportion = percent / 100 * GRAPH_LENGTH
    graph = BLOCKS[-1] * int(proportion + 0.5 / markers)
    remainder = int((proportion - len(graph)) * markers + 0.5)
    graph += BLOCKS[remainder] if remainder > 0 else ""
    return graph + BLOCKS[0] * (GRAPH_LENGTH - len(graph))


def format_duration(seconds: float) -> str:
    total_minutes = round(seconds / 60)
    hours, minutes = divmod(total_minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} {'hr' if hours == 1 else 'hrs'}")
    if minutes or not parts:
        parts.append(f"{minutes} {'min' if minutes == 1 else 'mins'}")
    return " ".join(parts)


def parse_duration(value: str) -> int | None:
    hours = re.search(r"(\d+(?:\.\d+)?)\s*hrs?", value)
    minutes = re.search(r"(\d+(?:\.\d+)?)\s*mins?", value)
    if not hours and not minutes:
        return None
    return round(float(hours.group(1)) * 3600 if hours else 0) + round(
        float(minutes.group(1)) * 60 if minutes else 0
    )


def activity_text(activity: dict[str, Any], total_seconds: int | None = None) -> str | None:
    if text := activity.get("text"):
        return str(text)
    if seconds := activity.get("total_seconds"):
        return format_duration(float(seconds))
    if total_seconds is not None and activity.get("percent") is not None:
        return format_duration(total_seconds * float(activity["percent"]) / 100)
    return None


def format_row(name: str, text: str, percent: float, name_width: int) -> str:
    return (
        f"{name.ljust(name_width)}   "
        f"{text:<{TIME_COLUMN_WIDTH}}{make_graph(percent)}   "
        f"{percent:05.2f} %"
    )


def render_stats(data: dict[str, Any], language_count: int = 5) -> str:
    languages = list(data.get("languages") or [])[:language_count]
    if not languages:
        raise ValueError("WakaTime returned no language activity")

    total_text = data.get("human_readable_total_including_other_language") or data.get(
        "human_readable_total"
    )
    total_seconds = parse_duration(str(total_text)) if total_text else data.get("total_seconds")
    if not total_text and total_seconds:
        total_text = format_duration(float(total_seconds))
    if not total_text:
        raise ValueError("WakaTime returned no total coding time")

    ai_coding = next(
        (category for category in data.get("categories") or [] if category.get("name") == "AI Coding"),
        None,
    )

    names = [str(language["name"]) for language in languages]
    if ai_coding:
        names.append("AI Coding")
    name_width = max(map(len, names))

    lines = [f"Total Time: {total_text}"]
    if ai_coding:
        ai_text = activity_text(ai_coding, total_seconds)
        if not ai_text:
            raise ValueError("WakaTime returned AI Coding activity without a duration")
        lines.extend(
            [
                format_row("AI Coding", ai_text, float(ai_coding["percent"]), name_width),
                "",
            ]
        )
    else:
        lines.append("")

    lines.extend(
        format_row(
            str(language["name"]),
            activity_text(language) or "0 mins",
            float(language["percent"]),
            name_width,
        )
        for language in languages
    )
    return "\n".join(lines)


def fetch_stats(api_key: str, time_range: str) -> dict[str, Any]:
    url = f"https://wakatime.com/api/v1/users/current/stats/{time_range}"
    authorization = base64.b64encode(api_key.encode()).decode()
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {authorization}",
            "User-Agent": "suemor233-profile-readme",
        },
    )

    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
            if errors := payload.get("error") or payload.get("errors"):
                raise RuntimeError(f"WakaTime API error: {errors}")
            return payload["data"]
        except urllib.error.HTTPError as error:
            if error.code not in {202, 429, 500, 502, 503, 504} or attempt == 4:
                raise
        time.sleep(10 * attempt)

    raise RuntimeError("Unable to fetch WakaTime stats")


def update_readme(path: Path, content: str) -> bool:
    readme = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    if len(pattern.findall(readme)) != 1:
        raise ValueError("README must contain exactly one WakaTime section")
    replacement = f"{START_MARKER}\n\n```txt\n{content}\n```\n\n{END_MARKER}"
    updated = pattern.sub(replacement, readme, count=1)
    if updated == readme:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", type=Path, default=Path("readme.md"))
    parser.add_argument("--time-range", default="last_7_days")
    parser.add_argument("--language-count", type=int, default=5)
    args = parser.parse_args()

    api_key = os.environ.get("WAKATIME_API_KEY")
    if not api_key:
        raise RuntimeError("WAKATIME_API_KEY is required")

    stats = fetch_stats(api_key, args.time_range)
    changed = update_readme(args.readme, render_stats(stats, args.language_count))
    print("README updated" if changed else "README already up to date")


if __name__ == "__main__":
    main()
