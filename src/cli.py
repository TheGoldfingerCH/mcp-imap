"""mcp-imap — point d'entrée : charge .env puis lance le serveur MCP IMAP."""
from __future__ import annotations

import os
import pathlib


def _load_env(env_file: pathlib.Path) -> None:
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    # Cherche .env dans le répertoire du projet (parent de src/)
    env_path = pathlib.Path(__file__).parent.parent / ".env"
    _load_env(env_path)

    # Ajoute le répertoire parent au path pour que 'src' soit trouvable
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

    from src.mcp_imap import main as run_mcp
    run_mcp()


if __name__ == "__main__":
    main()
