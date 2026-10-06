"""Email provider and SaaS tools from a domain's public DNS records.

MX records show who runs the company's email. SPF includes show who sends
email on its behalf (marketing, support, transactional). Verification TXT
records show which services it has verified the domain with. All public,
queried through the user's own resolver: no third-party API involved.

These are signals, not proof: records can be stale.
"""

import re
from dataclasses import asdict, dataclass, field

import dns.asyncresolver
import dns.exception
import dns.resolver

MX_PROVIDERS = [
    ("google.com", "Google Workspace"), ("googlemail.com", "Google Workspace"),
    ("outlook.com", "Microsoft 365"), ("zoho", "Zoho Mail"), ("protonmail", "Proton Mail"),
    ("pphosted.com", "Proofpoint"), ("mimecast", "Mimecast"),
    ("messagingengine.com", "Fastmail"), ("amazonaws.com", "Amazon SES"),
    ("mailgun.org", "Mailgun"), ("barracudanetworks.com", "Barracuda"),
]
SPF_SERVICES = [
    ("_spf.google.com", "Google Workspace"), ("spf.protection.outlook.com", "Microsoft 365"),
    ("sendgrid.net", "SendGrid"), ("mailgun.org", "Mailgun"), ("amazonses.com", "Amazon SES"),
    ("servers.mcsv.net", "Mailchimp"), ("mandrillapp.com", "Mailchimp Transactional"),
    ("_spf.salesforce.com", "Salesforce"), ("hubspotemail.net", "HubSpot"),
    ("mail.zendesk.com", "Zendesk"), ("spf.mtasv.net", "Postmark"),
    ("_spf.atlassian.net", "Atlassian"), ("helpscoutemail.com", "Help Scout"),
    ("mktomail.com", "Marketo"), ("sparkpostmail.com", "SparkPost"),
    ("freshdesk.com", "Freshdesk"), ("zoho.com", "Zoho"),
]
# Verification records with a non-generic shape. Anything shaped like
# "<name>-domain-verification=" or "<name>-site-verification=" is also picked up.
TXT_SERVICES = [
    ("MS=", "Microsoft 365"), ("docusign=", "DocuSign"), ("ZOOM_verify_", "Zoom"),
    ("stripe-verification=", "Stripe"), ("apple-domain-verification=", "Apple"),
    ("google-site-verification=", "Google"), ("facebook-domain-verification=", "Meta"),
    ("atlassian-domain-verification=", "Atlassian"), ("adobe-idp-site-verification=", "Adobe"),
]
_GENERIC_VERIFICATION = re.compile(r"^([a-z0-9][a-z0-9-]*?)-(?:domain|site)-verification=", re.I)


@dataclass
class DnsInfo:
    email_provider: list[str] = field(default_factory=list)
    email_senders: list[str] = field(default_factory=list)
    verified_services: list[str] = field(default_factory=list)
    # Record types that could not be read, so "none found" isn't mistaken for
    # "none exist". Large TXT answers need DNS over TCP, which some networks block.
    unavailable: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _add(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


def classify(mx_hosts: list[str], txt_records: list[str]) -> DnsInfo:
    info = DnsInfo()
    for host in mx_hosts:
        for needle, provider in MX_PROVIDERS:
            if needle in host.lower():
                _add(info.email_provider, provider)
    for record in txt_records:
        if record.lower().startswith("v=spf1"):
            for needle, service in SPF_SERVICES:
                if f"include:{needle}" in record.lower() or needle in record.lower():
                    _add(info.email_senders, service)
            continue
        for prefix, service in TXT_SERVICES:
            if record.startswith(prefix):
                _add(info.verified_services, service)
                break
        else:
            if m := _GENERIC_VERIFICATION.match(record):
                _add(info.verified_services, m.group(1).lower())
    return info


async def _records(resolver, domain: str, kind: str) -> list[str] | None:
    """The records, [] if there are none, or None if they could not be read."""
    try:
        answer = await resolver.resolve(domain, kind)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except (dns.resolver.NoNameservers, dns.exception.Timeout):
        return None
    if kind == "MX":
        return [str(r.exchange).rstrip(".") for r in answer]
    return [b"".join(r.strings).decode("utf-8", "replace") for r in answer]


async def lookup(domain: str, resolver=None) -> DnsInfo:
    if resolver is None:
        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = 8  # a large TXT answer is retried over TCP
    mx = await _records(resolver, domain, "MX")
    txt = await _records(resolver, domain, "TXT")
    info = classify(mx or [], txt or [])
    info.unavailable = [kind for kind, records in (("MX", mx), ("TXT", txt)) if records is None]
    return info
