"""Atomically attach operational settings without refreshing source timestamps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dashboard import export_dashboard, validate_dashboard_directory


def attach_settings(directory: Path, settings_path: Path) -> None:
    manifest = validate_dashboard_directory(directory)
    dashboard = json.loads((directory / 'dashboard.json').read_text(encoding='utf-8'))
    dashboard['settingsStatus'] = json.loads(settings_path.read_text(encoding='utf-8'))
    dashboard['quality'] = manifest['quality']
    dashboard['watermarks'] = manifest['watermarks']
    if any(item['path'] == 'research-v2.json' for item in manifest['files']):
        dashboard['researchSnapshot'] = json.loads(
            (directory / 'research-v2.json').read_text(encoding='utf-8'))
    dashboard['signals'] = [
        json.loads((directory / item['uri']).read_text(encoding='utf-8'))
        for item in manifest['signals']
    ]
    export_dashboard(
        dashboard, directory, run_id=str(manifest['runId']),
        as_of=str(manifest['asOf']), generated_at=str(manifest['generatedAt']),
        chunk_by_ticker=True,
    )
    validate_dashboard_directory(directory, require_settings=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    arguments = parser.parse_args()
    attach_settings(arguments.directory, arguments.settings)


if __name__ == '__main__':
    main()
