#!/usr/bin/env python3
from __future__ import annotations

import secrets
from pathlib import Path

path = Path(__file__).with_name(".env")
if path.exists():
    print(f"Using existing {path}")
else:
    path.write_text(
        "PILOT_POSTGRES_PASSWORD=" + secrets.token_urlsafe(32) + "\n"
        "TECTONIC_JWT_SHARED_SECRET=" + secrets.token_urlsafe(48) + "\n"
        "PILOT_LLM_MODE=mock\n"
        "PILOT_LLM_BASE_URL=\n"
        "PILOT_LLM_API_KEY=\n"
        "PILOT_LLM_CHAT_MODEL=\n"
        "PILOT_LLM_EMBEDDING_MODEL=\n"
    )
    path.chmod(0o600)
    print(f"Generated {path}")
