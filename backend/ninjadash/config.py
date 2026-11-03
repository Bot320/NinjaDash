"""Settings: read from an env-style file outside the repo, overridable by real environment variables."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ENV_CANDIDATES = [
    Path("/etc/ninjadash/ninjadash.env"),
    Path.home() / ".config/ninjadash/ninjadash.env",
]
RULES_CANDIDATES = [
    Path("/etc/ninjadash/classify.toml"),
    Path.home() / ".config/ninjadash/classify.toml",
]
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_RULES = PACKAGE_DIR.parent / "classify.toml"
DEFAULT_FRONTEND = PACKAGE_DIR.parent.parent / "frontend"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip()          # allow trailing comments
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def find_env_file() -> Path | None:
    explicit = os.environ.get("NINJADASH_ENV")
    if explicit:
        return Path(explicit)
    for p in ENV_CANDIDATES:
        if p.is_file():
            return p
    return None


def find_rules_file() -> Path:
    explicit = os.environ.get("NINJADASH_RULES")
    if explicit:
        return Path(explicit)
    for p in RULES_CANDIDATES:
        if p.is_file():
            return p
    return DEFAULT_RULES


def _default_history_db() -> str:
    if Path("/var/lib/ninjadash").is_dir() and os.access("/var/lib/ninjadash", os.W_OK):
        return "/var/lib/ninjadash/history.sqlite"
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "ninjadash"
    return str(state / "history.sqlite")


@dataclass
class Config:
    env_file: Path | None
    host: str = "eu.ninjarmm.com"
    base_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    scope: str = "monitoring"
    poll_fast: int = 60
    poll_slow: int = 300
    listen_host: str = "127.0.0.1"
    listen_port: int = 8080
    history_db: str = ""
    theme: str = "auto"
    light_from: str = "07:00"
    light_until: str = "19:00"
    demo: bool = False
    frontend_dir: Path = DEFAULT_FRONTEND
    rules_file: Path = DEFAULT_RULES
    rules: dict = field(default_factory=dict)

    @property
    def has_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def api_base(self) -> str:
        return (self.base_url or f"https://{self.host}").rstrip("/")


def load_config() -> Config:
    env_file = find_env_file()
    values: dict[str, str] = {}
    if env_file and env_file.is_file():
        values.update(parse_env_file(env_file))
    for key, val in os.environ.items():                  # real env wins (handy for tests)
        if key.startswith("NINJA_") or key in {
            "POLL_FAST", "POLL_SLOW", "LISTEN", "HISTORY_DB", "THEME", "LIGHT_FROM", "LIGHT_UNTIL", "DEMO",
        }:
            values[key] = val

    listen = values.get("LISTEN", "127.0.0.1:8080")
    host, _, port = listen.rpartition(":")
    cfg = Config(
        env_file=env_file,
        host=values.get("NINJA_HOST", "eu.ninjarmm.com") or "eu.ninjarmm.com",
        base_url=values.get("NINJA_BASE_URL", ""),
        client_id=values.get("NINJA_CLIENT_ID", ""),
        client_secret=values.get("NINJA_CLIENT_SECRET", ""),
        scope=values.get("NINJA_SCOPE", "monitoring") or "monitoring",
        poll_fast=max(30, int(values.get("POLL_FAST", "60") or 60)),
        poll_slow=max(60, int(values.get("POLL_SLOW", "300") or 300)),
        listen_host=host or "127.0.0.1",
        listen_port=int(port or 8080),
        history_db=values.get("HISTORY_DB") or _default_history_db(),
        theme=(values.get("THEME", "auto") or "auto").lower(),
        light_from=values.get("LIGHT_FROM", "07:00") or "07:00",
        light_until=values.get("LIGHT_UNTIL", "19:00") or "19:00",
        demo=(values.get("DEMO", "") or "").lower() in {"1", "true", "yes", "on"},
    )
    frontend = os.environ.get("NINJADASH_FRONTEND")
    if frontend:
        cfg.frontend_dir = Path(frontend)
    cfg.rules_file = find_rules_file()
    cfg.rules = load_rules(cfg.rules_file)
    return cfg


def load_rules(path: Path) -> dict:
    """User rules extend the built-in defaults: their [[rule]] entries are tried first."""
    with open(DEFAULT_RULES, "rb") as fh:
        base = tomllib.load(fh)
    if path.resolve() == DEFAULT_RULES.resolve() or not path.is_file():
        return base
    with open(path, "rb") as fh:
        user = tomllib.load(fh)
    merged = dict(base)
    for section in ("severity", "tiers", "display"):
        merged[section] = {**base.get(section, {}), **user.get(section, {})}
    merged["rule"] = list(user.get("rule", [])) + list(base.get("rule", []))
    return merged
