#!/usr/bin/env python3

from datetime import datetime

from packs import apply_pack_schedules


def main():
    now = datetime.now().isoformat()
    try:
        changes = apply_pack_schedules()
        if changes:
            print(f"[pack-scheduler] {now} cambios={len(changes)}")
            for change in changes:
                print(
                    f"[pack-scheduler] pack={change['pack']} previous={change['previous']} "
                    f"enabled={change['enabled']} window={change['window']}"
                )
        else:
            print(f"[pack-scheduler] {now} sin cambios")
    except Exception as exc:
        print(f"[pack-scheduler] {now} error={exc}")
        raise


if __name__ == "__main__":
    main()
