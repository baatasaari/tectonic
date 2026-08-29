"""Real end-to-end test for security/saml_verifier.py: a genuine RSA
keypair and self-signed X.509 certificate, a genuine XML-DSig-signed
SAML assertion built and signed with `signxml` itself, verified by the
real `XmlDsigSamlAssertionVerifier` -- real crypto throughout, the same
"real client, mocked/absent transport" shape `test_oidc_verifier.py`
gave OIDC (there is no live IdP to mock a transport for here at all:
everything SAML verification needs -- the certificate -- already lives
on the stored `IdentityProviderRecord`).
`StubSamlAssertionVerifier` (core/fakes.py) covers
SamlFederationService's own business logic without any of this; this
file is the one place the real cryptography actually gets exercised.
"""
from __future__ import annotations

import base64
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLSigner

from identity_and_access.core.domain import (
    FederationError,
    IdentityProviderRecord,
    IdentityProviderType,
)
from identity_and_access.security.saml_verifier import XmlDsigSamlAssertionVerifier

_NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
}
AUDIENCE = "identity-and-access"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-idp")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key_pem, cert_pem


def _provider(cert_pem: str, *, client_id: str = AUDIENCE) -> IdentityProviderRecord:
    return IdentityProviderRecord(
        id="p1", tenant_id="acme", name="ADFS", provider_type=IdentityProviderType.SAML,
        issuer="https://adfs.acme.com", client_id=client_id, x509_certificate=cert_pem,
    )


def _build_and_sign(
    key_pem,
    cert_pem,
    *,
    name_id: str | None = "alice@acme.com",
    not_before_delta: datetime.timedelta = datetime.timedelta(minutes=-5),
    not_on_or_after_delta: datetime.timedelta = datetime.timedelta(minutes=5),
    audience: str | None = AUDIENCE,
    attributes: dict[str, list[str]] | None = None,
    omit_conditions: bool = False,
) -> str:
    """Builds a real SAML Response containing one Assertion, signs the
    Assertion with a real XML-DSig signature, and returns the base64
    encoding a real HTTP-POST binding would carry in `SAMLResponse`."""
    now = datetime.datetime.now(datetime.UTC)
    issue_instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    not_before = (now + not_before_delta).strftime("%Y-%m-%dT%H:%M:%SZ")
    not_on_or_after = (now + not_on_or_after_delta).strftime("%Y-%m-%dT%H:%M:%SZ")
    attributes = attributes if attributes is not None else {"email": ["alice@acme.com"], "groups": ["engineering"]}

    subject_xml = (
        f'<saml:Subject><saml:NameID>{name_id}</saml:NameID></saml:Subject>' if name_id is not None else ""
    )
    conditions_xml = "" if omit_conditions else (
        f'<saml:Conditions NotBefore="{not_before}" NotOnOrAfter="{not_on_or_after}">'
        + (f'<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>'
           if audience is not None else "")
        + "</saml:Conditions>"
    )
    attribute_statement = "<saml:AttributeStatement>" + "".join(
        f'<saml:Attribute Name="{attr_name}">'
        + "".join(f"<saml:AttributeValue>{v}</saml:AttributeValue>" for v in values)
        + "</saml:Attribute>"
        for attr_name, values in attributes.items()
    ) + "</saml:AttributeStatement>"

    response_xml = f"""
    <samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                     xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                     ID="_response1" IssueInstant="{issue_instant}" Version="2.0">
      <saml:Issuer>https://adfs.acme.com</saml:Issuer>
      <saml:Assertion ID="_assertion1" IssueInstant="{issue_instant}" Version="2.0">
        <saml:Issuer>https://adfs.acme.com</saml:Issuer>
        {subject_xml}
        {conditions_xml}
        {attribute_statement}
      </saml:Assertion>
    </samlp:Response>
    """

    root = etree.fromstring(response_xml.encode())
    assertion = root.find(".//saml:Assertion", _NS)
    signed_assertion = XMLSigner(c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#").sign(
        assertion, key=key_pem, cert=cert_pem,
    )
    root.replace(assertion, signed_assertion)
    return base64.b64encode(etree.tostring(root)).decode()


async def test_verify_accepts_a_genuinely_signed_assertion(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(key_pem, cert_pem)

    verifier = XmlDsigSamlAssertionVerifier()
    claims = await verifier.verify(saml_response=saml_response, provider=_provider(cert_pem))

    assert claims["sub"] == "alice@acme.com"
    assert claims["email"] == "alice@acme.com"  # single value -> scalar
    assert claims["groups"] == "engineering"  # single value -> scalar (list only when >1)


async def test_verify_returns_a_list_for_a_multi_valued_attribute(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(
        key_pem, cert_pem, attributes={"email": ["alice@acme.com"], "groups": ["engineering", "admins"]},
    )

    claims = await XmlDsigSamlAssertionVerifier().verify(saml_response=saml_response, provider=_provider(cert_pem))

    assert claims["groups"] == ["engineering", "admins"]


async def test_verify_rejects_a_tampered_assertion(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(key_pem, cert_pem)
    tampered_xml = base64.b64decode(saml_response).replace(b"alice@acme.com", b"mallory@evil.com")
    tampered_response = base64.b64encode(tampered_xml).decode()

    with pytest.raises(FederationError):
        await XmlDsigSamlAssertionVerifier().verify(saml_response=tampered_response, provider=_provider(cert_pem))


async def test_verify_rejects_a_signature_from_an_untrusted_key(keypair):
    _key_pem, cert_pem = keypair
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key_pem = other_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    )
    other_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "attacker")])
    now = datetime.datetime.now(datetime.UTC)
    other_cert = (
        x509.CertificateBuilder()
        .subject_name(other_name).issuer_name(other_name).public_key(other_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=365))
        .sign(other_key, hashes.SHA256())
    )
    other_cert_pem = other_cert.public_bytes(serialization.Encoding.PEM).decode()

    # Signed with the attacker's own key/cert, but the *provider* still only trusts
    # the real IdP's cert -- must be rejected even though the signature is internally
    # self-consistent (a real, valid signature, just not from the trusted party).
    saml_response = _build_and_sign(other_key_pem, other_cert_pem)

    with pytest.raises(FederationError):
        await XmlDsigSamlAssertionVerifier().verify(saml_response=saml_response, provider=_provider(cert_pem))


async def test_verify_rejects_an_expired_assertion(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(
        key_pem, cert_pem,
        not_before_delta=datetime.timedelta(minutes=-10), not_on_or_after_delta=datetime.timedelta(minutes=-5),
    )

    with pytest.raises(FederationError, match="expired"):
        await XmlDsigSamlAssertionVerifier().verify(saml_response=saml_response, provider=_provider(cert_pem))


async def test_verify_rejects_an_assertion_not_yet_valid(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(
        key_pem, cert_pem,
        not_before_delta=datetime.timedelta(minutes=5), not_on_or_after_delta=datetime.timedelta(minutes=10),
    )

    with pytest.raises(FederationError, match="not yet valid"):
        await XmlDsigSamlAssertionVerifier().verify(saml_response=saml_response, provider=_provider(cert_pem))


async def test_verify_rejects_a_wrong_audience(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(key_pem, cert_pem, audience="some-other-sp")

    with pytest.raises(FederationError, match="audience"):
        await XmlDsigSamlAssertionVerifier().verify(
            saml_response=saml_response, provider=_provider(cert_pem, client_id=AUDIENCE),
        )


async def test_verify_rejects_a_missing_name_id(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(key_pem, cert_pem, name_id=None)

    with pytest.raises(FederationError, match="NameID"):
        await XmlDsigSamlAssertionVerifier().verify(saml_response=saml_response, provider=_provider(cert_pem))


async def test_verify_rejects_malformed_base64(keypair):
    _key_pem, cert_pem = keypair

    with pytest.raises(FederationError):
        await XmlDsigSamlAssertionVerifier().verify(saml_response="not valid base64!!!", provider=_provider(cert_pem))


async def test_verify_rejects_malformed_xml(keypair):
    _key_pem, cert_pem = keypair
    bad_xml = base64.b64encode(b"this is not xml").decode()

    with pytest.raises(FederationError):
        await XmlDsigSamlAssertionVerifier().verify(saml_response=bad_xml, provider=_provider(cert_pem))


async def test_verify_raises_when_provider_has_no_certificate_configured(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(key_pem, cert_pem)
    provider = IdentityProviderRecord(
        id="p1", tenant_id="acme", name="ADFS", provider_type=IdentityProviderType.SAML,
        issuer="https://adfs.acme.com",
    )

    with pytest.raises(FederationError):
        await XmlDsigSamlAssertionVerifier().verify(saml_response=saml_response, provider=provider)


async def test_verify_accepts_an_assertion_with_no_conditions_element(keypair):
    key_pem, cert_pem = keypair
    saml_response = _build_and_sign(key_pem, cert_pem, omit_conditions=True)

    claims = await XmlDsigSamlAssertionVerifier().verify(saml_response=saml_response, provider=_provider(cert_pem))

    assert claims["sub"] == "alice@acme.com"
