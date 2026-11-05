"""
test_api_http.py
================
Prueba de integración de los endpoints de Sentinel en FastAPI.
Invoca directamente los handlers de FastAPI y los contratos de datos
Pydantic para validar sin depender de sockets de red.
"""
import sys, os, json, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configurar archivo temporal para config.json
tmp_dir = tempfile.mkdtemp()
os.environ["SAFELOCK_CONFIG"] = os.path.join(tmp_dir, "config.json")

import main as app_module
import sentinel_connector
from main import (
    read_sentinel_status,
    change_sentinel_mode,
    block_sentinel_domain,
    SentinelModePayload,
    SentinelBlockPayload
)
from fastapi import HTTPException

# Mock para no requerir Docker en Windows
sentinel_connector.reload_pihole_dns = lambda: True

GRN  = "\033[92m"
RED  = "\033[91m"
CYN  = "\033[96m"
BLD  = "\033[1m"
RST  = "\033[0m"
PASS = f"{GRN}✓ PASS{RST}"
FAIL = f"{RED}✗ FAIL{RST}"

results = []

def check(name, cond, detail=""):
    tag = PASS if cond else FAIL
    suffix = f"  {detail}" if detail else ""
    print(f"  {tag}  {name}{suffix}")
    results.append((name, cond))

print(f"\n{BLD}{CYN}═══ TEST API: Endpoints Sentinel (Handlers + Pydantic) ═══{RST}\n")

# 1. GET /sentinel/status
print(f"{BLD}TEST API-1: read_sentinel_status(){RST}")
data = read_sentinel_status()
check("Retorna dict", isinstance(data, dict))
check("Tiene 'mode'", "mode" in data)
check("Tiene 'devices'", "devices" in data)
check("devices es lista", isinstance(data.get("devices"), list))
check("Tiene 'dispositivos'", "dispositivos" in data)
check("Tiene 'last_run'", "last_run" in data)
check("mode es 'shadow' o 'protect'", data.get("mode") in ("shadow", "protect"))
print(f"  → Respuesta: mode={data.get('mode')!r}, total={data.get('total_dispositivos')}")
print()

# 2. POST /sentinel/mode shadow
print(f"{BLD}TEST API-2: change_sentinel_mode('shadow'){RST}")
payload_shadow = SentinelModePayload(mode="shadow")
res_shadow = change_sentinel_mode(payload_shadow)
check("success en respuesta", res_shadow.get("success") is True)
check("mode es 'shadow'", res_shadow.get("mode") == "shadow")
print(f"  → Respuesta: {json.dumps(res_shadow)}")
print()

# 3. POST /sentinel/mode protect
print(f"{BLD}TEST API-3: change_sentinel_mode('protect'){RST}")
payload_protect = SentinelModePayload(mode="protect")
res_protect = change_sentinel_mode(payload_protect)
check("success en respuesta", res_protect.get("success") is True)
check("mode es 'protect'", res_protect.get("mode") == "protect")
print(f"  → Respuesta: {json.dumps(res_protect)}")
print()

# 4. POST /sentinel/mode inválido
print(f"{BLD}TEST API-4: change_sentinel_mode con modo inválido{RST}")
error_atrapado = False
try:
    change_sentinel_mode(SentinelModePayload(mode="MODO_INVALIDO"))
except HTTPException as e:
    error_atrapado = True
    check("HTTPException 400 lanzada", e.status_code == 400, f"code={e.status_code}")
except Exception as e:
    check("HTTPException esperada", False, f"otra excepción: {e}")
if not error_atrapado:
    check("Debe lanzar excepción", False)
print()

# 5. POST /sentinel/block
print(f"{BLD}TEST API-5: block_sentinel_domain{RST}")
payload_block = SentinelBlockPayload(domain="malware-c2.test.xyz", enabled=True)
try:
    res_block = block_sentinel_domain(payload_block)
    check("success es True", res_block.get("success") is True)
    check("domain coincide", res_block.get("domain") == "malware-c2.test.xyz")
    check("enabled es True", res_block.get("enabled") is True)
    print(f"  → Respuesta: {json.dumps(res_block)}")
except Exception as e:
    check("block ejecutado sin crash", False, str(e))
print()

# 6. Volver a shadow
change_sentinel_mode(SentinelModePayload(mode="shadow"))

# 7. Resumen de resultados
total  = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed

print(f"{BLD}{'═'*50}")
print(f"  RESULTADO API: {passed}/{total} tests pasados", end="")
if failed:
    print(f"  {RED}({failed} FALLIDOS){RST}", end="")
print(f"\n{'═'*50}{RST}\n")

sys.exit(0 if failed == 0 else 1)
