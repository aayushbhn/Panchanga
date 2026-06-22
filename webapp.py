"""The shared Flask application instance, imported by routes.py and views.py."""
from urllib.parse import urlparse

from flask import Flask, request

app = Flask(__name__)


# ============================================================
# CORS — allow the public websites to call the API from the browser
# ============================================================
# Registrable domains permitted to make cross-origin requests. Any subdomain
# (e.g. www.) and either scheme (http/https) of these is allowed; the exact
# Origin is echoed back (required by browsers). Non-browser callers send no
# Origin and are unaffected. Dependency-free — no flask-cors needed.
ALLOWED_ORIGIN_DOMAINS = (
    "nepalirudraksha.com",
    "neparudraksha.com",
)


def _allowed_origin(origin):
    """Return the Origin to echo if it (or a subdomain) is allowed, else None."""
    if not origin:
        return None
    try:
        host = (urlparse(origin).hostname or "").lower()
    except Exception:
        return None
    if not host:
        return None
    for domain in ALLOWED_ORIGIN_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return origin
    return None


@app.after_request
def _apply_cors(response):
    origin = _allowed_origin(request.headers.get("Origin"))
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        # Echo the headers the browser asked for in preflight, else a sane default.
        requested = request.headers.get("Access-Control-Request-Headers")
        response.headers["Access-Control-Allow-Headers"] = requested or "Content-Type, Authorization"
        response.headers["Access-Control-Max-Age"] = "86400"
    return response
