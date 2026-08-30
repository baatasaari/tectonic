"""Real SAML 2.0 assertion verification -- closes the gap
`core/oidc_federation_service.py` and this module's README used to
document: "a real SAML assertion consumer is real, non-trivial
cryptographic work ... out of scope for this pass."

Verifies the HTTP-POST-bound `SAMLResponse` form value (base64-encoded
XML) with `signxml`: its XML digital signature is checked against the
tenant's registered IdP certificate (`provider.x509_certificate`),
constrained to the exact expected `Assertion` location via
`SignatureConfiguration(location=...)` -- `signxml`'s own documented
SAML best practice, and this is the real defense against a basic
signature-wrapping attack (an attacker appending a second, unsigned or
differently-signed `Assertion` elsewhere in the document while leaving
the genuinely-signed one in place, hoping a naive XPath grabs the wrong
one). Only `signxml`'s own returned `signed_xml` element is ever read
from afterward -- never the raw, untrusted input tree -- the same
"see what is signed" rule `signxml`'s own docs lead with.

Once the signature is verified, `Conditions/@NotBefore`/
`@NotOnOrAfter` and `Conditions/AudienceRestriction` are validated by
hand (`signxml` verifies the *signature*, not SAML's own semantic
constraints -- those are this module's job, same as PyJWT verifying a
JWT's signature but leaving `exp`/`aud` checks to the caller in
`security/oidc_verifier.py`). `provider.client_id` is reused as this
SP's expected audience/entityID -- the same config field OIDC already
uses for the analogous "who is this token/assertion for" check, rather
than adding a second, SAML-only field for an identical concept.
"""
from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import Any

from lxml import etree
from signxml import SignatureConfiguration, XMLVerifier
from signxml.exceptions import SignXMLException

from identity_and_access.core.domain import FederationError, IdentityProviderRecord

_SAML_ASSERTION_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
_NS = {"saml": _SAML_ASSERTION_NS}
_ASSERTION_LOCATION = f"./{{{_SAML_ASSERTION_NS}}}Assertion/"
_INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class XmlDsigSamlAssertionVerifier:
    async def verify(self, *, saml_response: str, provider: IdentityProviderRecord) -> dict[str, Any]:
        if not provider.x509_certificate:
            raise FederationError(f"identity provider {provider.id} has no x509_certificate configured")

        try:
            xml_bytes = base64.b64decode(saml_response)
        except binascii.Error as exc:
            raise FederationError(f"SAMLResponse is not valid base64: {exc}") from exc

        config = SignatureConfiguration(location=_ASSERTION_LOCATION)
        try:
            result = XMLVerifier().verify(xml_bytes, x509_cert=provider.x509_certificate, expect_config=config)
        except etree.XMLSyntaxError as exc:
            raise FederationError(f"SAMLResponse is not well-formed XML: {exc}") from exc
        except SignXMLException as exc:
            raise FederationError(f"SAML assertion signature verification failed: {exc}") from exc

        # Only the verified element is trusted from here on -- never the raw input tree.
        assertion = result.signed_xml
        return self._extract_claims(assertion, provider)

    def _extract_claims(self, assertion: Any, provider: IdentityProviderRecord) -> dict[str, Any]:
        name_id_el = assertion.find("./saml:Subject/saml:NameID", _NS)
        subject = (name_id_el.text or "").strip() if name_id_el is not None else ""
        if not subject:
            raise FederationError("SAML assertion is missing a Subject/NameID")

        self._validate_conditions(assertion, provider)

        claims: dict[str, Any] = {"sub": subject}
        for attribute in assertion.findall("./saml:AttributeStatement/saml:Attribute", _NS):
            name = attribute.get("Name")
            if not name:
                continue
            values = [(v.text or "").strip() for v in attribute.findall("./saml:AttributeValue", _NS)]
            values = [v for v in values if v]
            if not values:
                continue
            claims[name] = values[0] if len(values) == 1 else values
        return claims

    def _validate_conditions(self, assertion: Any, provider: IdentityProviderRecord) -> None:
        conditions = assertion.find("./saml:Conditions", _NS)
        if conditions is None:
            return  # some IdPs omit Conditions entirely -- nothing to enforce

        current = datetime.now(UTC)
        not_before = conditions.get("NotBefore")
        if not_before and current < _parse_instant(not_before):
            raise FederationError("SAML assertion is not yet valid (before its Conditions/@NotBefore)")
        not_on_or_after = conditions.get("NotOnOrAfter")
        if not_on_or_after and current >= _parse_instant(not_on_or_after):
            raise FederationError("SAML assertion has expired (past its Conditions/@NotOnOrAfter)")

        if provider.client_id:
            audiences = [
                (a.text or "").strip() for a in conditions.findall("./saml:AudienceRestriction/saml:Audience", _NS)
            ]
            audiences = [a for a in audiences if a]
            if audiences and provider.client_id not in audiences:
                raise FederationError(
                    f"SAML assertion audience {audiences!r} does not include the expected "
                    f"{provider.client_id!r} (identity provider's configured client_id)",
                )


def _parse_instant(value: str) -> datetime:
    try:
        return datetime.strptime(value, _INSTANT_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise FederationError(f"malformed SAML timestamp: {value!r}") from exc
