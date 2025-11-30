"""
WHOIS collector - gathers domain registration information.
"""

import re
from datetime import datetime

from .base import BaseCollector
from ..core.models import CompanyProfile, DataPoint, DataSourceType, ConfidenceLevel


class WhoisCollector(BaseCollector):
    """Collects WHOIS data for company domain."""

    source_type = DataSourceType.WHOIS
    name = "WHOIS Lookup"
    description = "Gathers domain registration and ownership information"
    priority = 1

    async def collect(self, profile: CompanyProfile, iteration: int) -> list[DataPoint]:
        """Collect WHOIS data."""
        data_points = []
        domain = profile.domain

        # Use multiple WHOIS API services
        whois_data = await self._fetch_whois_data(domain)

        if whois_data:
            source_url = f"whois://{domain}"

            # Registration date
            if "creation_date" in whois_data:
                data_points.append(self.create_data_point(
                    key="domain_created",
                    value=whois_data["creation_date"],
                    source_url=source_url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration,
                    metadata={"type": "date"}
                ))

                # Calculate domain age
                try:
                    created = datetime.fromisoformat(whois_data["creation_date"].replace("Z", "+00:00"))
                    age_years = (datetime.now(created.tzinfo) - created).days / 365.25
                    data_points.append(self.create_data_point(
                        key="domain_age_years",
                        value=str(round(age_years, 1)),
                        source_url=source_url,
                        confidence=ConfidenceLevel.HIGH,
                        iteration=iteration
                    ))
                except (ValueError, TypeError):
                    pass

            # Expiration date
            if "expiration_date" in whois_data:
                data_points.append(self.create_data_point(
                    key="domain_expires",
                    value=whois_data["expiration_date"],
                    source_url=source_url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

            # Registrar
            if "registrar" in whois_data:
                data_points.append(self.create_data_point(
                    key="domain_registrar",
                    value=whois_data["registrar"],
                    source_url=source_url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

            # Registrant (if available)
            if "registrant_name" in whois_data:
                data_points.append(self.create_data_point(
                    key="registrant_name",
                    value=whois_data["registrant_name"],
                    source_url=source_url,
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))

            if "registrant_org" in whois_data:
                data_points.append(self.create_data_point(
                    key="registrant_organization",
                    value=whois_data["registrant_org"],
                    source_url=source_url,
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))

            # Country
            if "registrant_country" in whois_data:
                data_points.append(self.create_data_point(
                    key="registrant_country",
                    value=whois_data["registrant_country"],
                    source_url=source_url,
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))

            # Name servers
            if "name_servers" in whois_data:
                data_points.append(self.create_data_point(
                    key="name_servers",
                    value=", ".join(whois_data["name_servers"]),
                    source_url=source_url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

            # DNSSEC
            if "dnssec" in whois_data:
                data_points.append(self.create_data_point(
                    key="dnssec_enabled",
                    value=str(whois_data["dnssec"]),
                    source_url=source_url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

        return data_points

    async def _fetch_whois_data(self, domain: str) -> dict:
        """Fetch WHOIS data from various sources."""
        # Try RDAP first (modern WHOIS replacement)
        rdap_data = await self._fetch_rdap(domain)
        if rdap_data:
            return rdap_data

        # Fallback: try to parse from web-based WHOIS
        web_whois = await self._fetch_web_whois(domain)
        if web_whois:
            return web_whois

        return {}

    async def _fetch_rdap(self, domain: str) -> dict:
        """Fetch data from RDAP service."""
        # Determine TLD and appropriate RDAP server
        tld = domain.split(".")[-1].lower()

        rdap_servers = {
            "com": "https://rdap.verisign.com/com/v1/domain/",
            "net": "https://rdap.verisign.com/net/v1/domain/",
            "org": "https://rdap.publicinterestregistry.org/rdap/domain/",
            "io": "https://rdap.nic.io/domain/",
            "co": "https://rdap.nic.co/domain/",
            "ru": "https://rdap.tcinet.ru/rdap/domain/",
        }

        rdap_url = rdap_servers.get(tld, f"https://rdap.org/domain/")
        full_url = f"{rdap_url}{domain}"

        data = await self.fetch_json(full_url)
        if not data:
            return {}

        result = {}

        # Parse RDAP response
        events = data.get("events", [])
        for event in events:
            action = event.get("eventAction", "")
            date = event.get("eventDate", "")
            if action == "registration":
                result["creation_date"] = date
            elif action == "expiration":
                result["expiration_date"] = date

        # Entities (registrant, registrar, etc.)
        for entity in data.get("entities", []):
            roles = entity.get("roles", [])
            vcard = entity.get("vcardArray", [])

            if "registrar" in roles:
                result["registrar"] = entity.get("handle", "")
                # Try to get registrar name from vcard
                if len(vcard) > 1:
                    for item in vcard[1]:
                        if item[0] == "fn":
                            result["registrar"] = item[3]
                            break

            if "registrant" in roles:
                if len(vcard) > 1:
                    for item in vcard[1]:
                        if item[0] == "fn":
                            result["registrant_name"] = item[3]
                        elif item[0] == "org":
                            result["registrant_org"] = item[3]
                        elif item[0] == "adr":
                            if isinstance(item[3], list) and len(item[3]) > 5:
                                result["registrant_country"] = item[3][6]

        # Name servers
        nameservers = data.get("nameservers", [])
        if nameservers:
            result["name_servers"] = [ns.get("ldhName", "") for ns in nameservers]

        # DNSSEC
        secure_dns = data.get("secureDNS", {})
        result["dnssec"] = secure_dns.get("delegationSigned", False)

        return result

    async def _fetch_web_whois(self, domain: str) -> dict:
        """Fallback: fetch from web-based WHOIS service."""
        url = f"https://www.whois.com/whois/{domain}"
        html = await self.fetch_url(url)

        if not html:
            return {}

        result = {}

        # Parse common patterns
        patterns = {
            "creation_date": r"Creat(?:ion|ed)\s*Date[:\s]+(\d{4}-\d{2}-\d{2})",
            "expiration_date": r"Expir(?:ation|y)\s*Date[:\s]+(\d{4}-\d{2}-\d{2})",
            "registrar": r"Registrar[:\s]+([^\n<]+)",
            "registrant_org": r"Registrant\s*Organization[:\s]+([^\n<]+)",
            "registrant_country": r"Registrant\s*Country[:\s]+([A-Z]{2})",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, html, re.I)
            if match:
                result[key] = match.group(1).strip()

        return result

    def discover_sources(self, profile: CompanyProfile) -> list[str]:
        """Discover sources from WHOIS data."""
        sources = []

        for dp in profile.get_data_by_source(self.source_type):
            # Registrant organization can lead to other domains
            if dp.key == "registrant_organization":
                sources.append(f"search:company:{dp.value}")

        return sources
