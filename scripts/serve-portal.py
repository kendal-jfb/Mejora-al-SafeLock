#!/usr/bin/env python3
"""Servidor estatico del portal SafeLock.

Sustituye a `npm run dev/build` en el dispositivo: el portal ya viene compilado
dentro del release (portal_dist/), asi que el SoC no necesita node ni npm.

Uso: serve-portal.py [--dir RUTA] [--port 5173]
"""

import argparse
import os
import posixpath
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_DIR = "/opt/safelock/current/portal_dist"
DEFAULT_PORT = 5173


class SPAHandler(SimpleHTTPRequestHandler):
    """Sirve archivos estaticos con fallback a index.html (rutas del SPA)."""

    def translate_path(self, path):
        local = super().translate_path(path)
        if os.path.isdir(local):
            if os.path.exists(os.path.join(local, "index.html")):
                return local
        if not os.path.exists(local):
            # Una ruta del router (sin extension) debe devolver el index.
            name = posixpath.basename(path.split("?", 1)[0].split("#", 1)[0])
            if "." not in name:
                return os.path.join(self.directory, "index.html")
        return local

    def end_headers(self):
        # El portal se sirve en LAN y cambia con cada release: sin cache.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        # journald ya pone marca de tiempo; evitamos duplicarla.
        sys.stderr.write("%s\n" % (fmt % args))


def main():
    ap = argparse.ArgumentParser(description="Servidor estatico del portal")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        sys.stderr.write(f"portal: no existe el directorio {args.dir}\n")
        return 1

    handler = lambda *a, **kw: SPAHandler(*a, directory=args.dir, **kw)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    sys.stderr.write(f"portal: sirviendo {args.dir} en 0.0.0.0:{args.port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
