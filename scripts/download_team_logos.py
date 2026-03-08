#!/usr/bin/env python3
"""
Download F1 team logo assets into assets/team_logos.

Source: Wikimedia Commons file URLs via Special:FilePath.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from pathlib import Path

TEAM_FILES = {
    "ferrari": "Scuderia Ferrari HP logo 24.svg",
    "mercedes": "Mercedes-AMG Petronas F1 Team logo (2026).svg",
    "red-bull-racing": "Red Bull Racing Logo 2026.svg",
    "mclaren": "McLaren Mastercard F1.jpg",
    "williams": "Atlassian Williams F1 Team logo.svg",
    "haas-f1-team": "TGR Haas F1 Team Logo (2026).svg",
    "aston-martin": "Aston Martin Aramco 2024 logo.png",
    "alpine": "BWT Alpine F1 Team Logo.png",
    "racing-point": "BWT Racing Point Logo.svg",
    "force-india": "Force India.svg",
    "renault": "Renault F1 Team logo 2019.svg",
    "toro-rosso": "Scuderia Toro Rosso logo.svg",
    "alphatauri": "Scuderia Alpha-Tauri.svg",
    "rb": "VCARB F1 logo.svg",
    "racing-bulls": "VCARB F1 logo.svg",
    "sauber": "Sauber Motorsport SVG logo (2023).svg",
    "alfa-romeo-racing": "Alfa Romeo F1 Team Stake Logo.svg",
    "alfa-romeo": "Alfa Romeo F1 Team Stake Logo.svg",
    "kick-sauber": "Logo Sauber F1.png",
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "assets" / "team_logos"
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": "Mozilla/5.0 (team-logo-fetcher)"}
    ok = 0
    fail = 0

    for stem, commons_file in TEAM_FILES.items():
        suffix = Path(commons_file).suffix.lower() or ".svg"
        out_path = out_dir / f"{stem}{suffix}"
        try:
            data = b""
            errors = []
            for base in (
                "https://commons.wikimedia.org/wiki/Special:FilePath/",
                "https://en.wikipedia.org/wiki/Special:FilePath/",
            ):
                url = base + urllib.parse.quote(commons_file)
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = resp.read()
                    if data:
                        break
                except Exception as err:
                    errors.append(str(err))
            if not data:
                raise RuntimeError("; ".join(errors) if errors else "empty file")
            out_path.write_bytes(data)
            ok += 1
            print(f"OK   {out_path.name}")
        except Exception as exc:
            fail += 1
            print(f"FAIL {stem}: {exc}")

    print(f"\nDone. success={ok}, failed={fail}, dir={out_dir}")


if __name__ == "__main__":
    main()
