from __future__ import annotations

import pytest

from secrets_and_credential_management.core.fakes import (
    InMemorySecretsRepository,
    StubAuditabilityClient,
    StubIdentityAccessClient,
)
from secrets_and_credential_management.core.rotation_service import RotationService
from secrets_and_credential_management.core.secret_access_service import SecretAccessService
from secrets_and_credential_management.core.secret_registry_service import SecretRegistryService
from secrets_and_credential_management.security.envelope_encryption import EnvelopeCipher

TEST_MASTER_KEY = "TjDlTNIHnInVxA0zsGHYi6iTjBRtCSnWVcGxrYLXaYc="


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemorySecretsRepository()
        self.cipher = EnvelopeCipher(master_key=kwargs.get("master_key", TEST_MASTER_KEY))
        self.identity_access = kwargs.get("identity_access") or StubIdentityAccessClient()
        self.auditability = kwargs.get("auditability") or StubAuditabilityClient()

        self.registry_service = SecretRegistryService(self.repository, self.cipher)
        self.access_service = SecretAccessService(
            self.repository, self.cipher, self.identity_access, self.auditability,
        )
        self.rotation_service = RotationService(self.repository, self.cipher)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
