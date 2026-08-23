"""Object storage adapter — deviation from the LLD's S3-compatible object
storage: no cloud credentials are available in this build environment, so
`FileBlobStorage` implements the same `BlobStorage` port against a local
(or mounted) directory, content-addressed by the blob's own SHA-256 hash
(matching the Version Manager's own hashing scheme). Swapping in a real
S3-compatible backend (AWS S3, GCS, Azure Blob) means implementing the
same `put`/`get` interface, e.g. via `boto3`/`aioboto3`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


class FileBlobStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(self, content: bytes) -> str:
        ref = hashlib.sha256(content).hexdigest()
        path = self._root / ref
        if not path.exists():
            path.write_bytes(content)
        return ref

    async def get(self, blob_ref: str) -> bytes:
        return (self._root / blob_ref).read_bytes()
