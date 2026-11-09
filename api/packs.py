import json
import os
import re
import sqlite3
import subprocess
import tempfile
from datetime import datetime

# Los datos (bind mounts de docker) siguen donde los dejo el aprovisionamiento;
# el codigo se mueve entre releases, los datos no.
DATA_DIR = os.environ.get("SAFELOCK_DATA_DIR", "")
if not DATA_DIR:
    if os.path.exists("/root/safeLock_SoC"):
        DATA_DIR = "/root/safeLock_SoC"
    elif os.path.exists("/data"):
        DATA_DIR = "/data"
    else:
        DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# La configuracion del cliente debe sobrevivir a las actualizaciones, asi que
# tras migrar vive fuera del arbol de releases. Mientras no exista la ruta
# nueva se sigue usando la vieja, para no perder la config de los equipos
# que aun no han migrado.
LEGACY_CONFIG_FILE = f"{DATA_DIR}/api/config.json"
CONFIG_FILE = os.environ.get("SAFELOCK_CONFIG", "")
if not CONFIG_FILE:
    CONFIG_FILE = ("/etc/safelock/config.json"
                   if os.path.exists("/etc/safelock/config.json")
                   else LEGACY_CONFIG_FILE)

PIHOLE_GRAVITY_DB = f"{DATA_DIR}/pihole/etc-pihole/gravity.db"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_FREQUENCIES = {"diario", "semanal", "quincenal", "mensual"}
DEFAULT_USER_CONFIG = {
    "email": "",
    "frequency": "semanal",
    "alerts_enabled": True,
}

PACK_IDS = (
    "PACK_FAMILY",
    "PACK_DETOX",
    "PACK_GAMES",
    "PACK_PRIVACY",
)

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DEFAULT_SCHEDULE = {"start": "", "end": "", "enabled": False}


def load_full_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def get_public_config():
    full_config = load_full_config()
    config = DEFAULT_USER_CONFIG.copy()

    email = str(full_config.get("email", "") or "").strip()
    frequency = str(full_config.get("frequency", DEFAULT_USER_CONFIG["frequency"]) or "").strip().lower()
    alerts_enabled = full_config.get("alerts_enabled", DEFAULT_USER_CONFIG["alerts_enabled"])

    config["email"] = email if EMAIL_RE.match(email) else ""
    config["frequency"] = frequency if frequency in ALLOWED_FREQUENCIES else DEFAULT_USER_CONFIG["frequency"]
    config["alerts_enabled"] = bool(alerts_enabled)
    return config


def save_full_config(data):
    config_dir = os.path.dirname(CONFIG_FILE)
    os.makedirs(config_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", dir=config_dir, delete=False) as tmp:
        json.dump(data, tmp)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name

    os.replace(tmp_path, CONFIG_FILE)


def validate_pack(pack):
    if pack not in PACK_IDS:
        raise ValueError(f"Pack inválido: {pack}")


def validate_schedule(start, end):
    start = (start or "").strip()
    end = (end or "").strip()

    if not start and not end:
        return "", "", False

    if not start or not end:
        raise ValueError("Debe indicar hora de inicio y fin, o limpiar ambas.")

    if not TIME_RE.match(start) or not TIME_RE.match(end):
        raise ValueError("Las horas deben tener formato HH:MM.")

    return start, end, True


def normalize_schedule(schedule):
    schedule = schedule if isinstance(schedule, dict) else {}
    start = str(schedule.get("start", "") or "").strip()
    end = str(schedule.get("end", "") or "").strip()
    enabled = bool(schedule.get("enabled", False))

    try:
        if enabled or start or end:
            start, end, has_window = validate_schedule(start, end)
            enabled = bool(enabled) and has_window
        else:
            start, end, enabled = "", "", False
    except ValueError:
        start, end, enabled = "", "", False

    return {"start": start, "end": end, "enabled": enabled}


def get_schedule_map():
    config = load_full_config()
    stored = config.get("pack_schedules", {})
    result = {}

    for pack in PACK_IDS:
        result[pack] = normalize_schedule(stored.get(pack, {}))

    return result


def save_schedule(pack, start, end, enabled):
    validate_pack(pack)
    start, end, has_window = validate_schedule(start, end)

    config = load_full_config()
    schedules = config.get("pack_schedules", {})
    schedules = schedules if isinstance(schedules, dict) else {}

    if has_window:
        schedules[pack] = {"start": start, "end": end, "enabled": bool(enabled)}
    else:
        schedules.pop(pack, None)

    config["pack_schedules"] = schedules
    save_full_config(config)

    return normalize_schedule(schedules.get(pack, {}))


def get_pack_states():
    conn = sqlite3.connect(PIHOLE_GRAVITY_DB)
    conn.row_factory = sqlite3.Row
    curr = conn.cursor()
    rows = curr.execute(
        "SELECT comment, enabled FROM domainlist WHERE comment LIKE '[PACK_%]'"
    ).fetchall()
    conn.close()

    states = {pack: False for pack in PACK_IDS}
    for row in rows:
        pack_name = row["comment"].strip("[]")
        if pack_name in states:
            states[pack_name] = bool(row["enabled"])
    return states


def set_pack_enabled(pack, enabled, source="manual"):
    validate_pack(pack)

    conn = sqlite3.connect(PIHOLE_GRAVITY_DB, timeout=10.0)
    try:
        curr = conn.cursor()
        comment_tag = f"[{pack}]"
        new_status = 1 if enabled else 0
        curr.execute("UPDATE domainlist SET enabled = ? WHERE comment = ?", (new_status, comment_tag))

        if curr.rowcount == 0:
            raise ValueError(f"No se encontró el pack {pack} en gravity.db")

        conn.commit()
    finally:
        conn.close()

    reload_result = subprocess.run(
        ["docker", "exec", "pihole", "pihole", "reloaddns"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if reload_result.returncode != 0:
        raise RuntimeError(reload_result.stderr.strip() or "No se pudo recargar Pi-hole")

    print(
        f"[packs] {datetime.now().isoformat()} source={source} pack={pack} enabled={bool(enabled)}"
    )
    return {"success": True, "pack": pack, "enabled": bool(enabled), "source": source}


def get_pack_schedules_with_state():
    schedules = get_schedule_map()
    states = get_pack_states()
    result = {}

    for pack in PACK_IDS:
        result[pack] = {
            "start": schedules[pack]["start"],
            "end": schedules[pack]["end"],
            "enabled": schedules[pack]["enabled"],
            "active_now": states.get(pack, False),
        }

    return result


def _time_to_minutes(value):
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def is_time_in_window(current_time, start, end):
    if not start or not end:
        return False

    start_minutes = _time_to_minutes(start)
    end_minutes = _time_to_minutes(end)
    current_minutes = current_time.hour * 60 + current_time.minute

    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def apply_pack_schedules(now=None):
    now = now or datetime.now()
    states = get_pack_states()
    schedules = get_schedule_map()
    changes = []

    for pack, schedule in schedules.items():
        if not schedule["enabled"] or not schedule["start"] or not schedule["end"]:
            continue

        desired_state = is_time_in_window(now, schedule["start"], schedule["end"])
        current_state = states.get(pack, False)

        if current_state == desired_state:
            continue

        result = set_pack_enabled(pack, desired_state, source="schedule")
        changes.append(
            {
                "pack": pack,
                "enabled": desired_state,
                "previous": current_state,
                "window": f'{schedule["start"]}-{schedule["end"]}',
                "result": result,
            }
        )

    return changes
