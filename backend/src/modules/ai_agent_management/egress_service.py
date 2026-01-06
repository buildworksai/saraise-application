"""Egress Allowlisting Service.

Implements egress allowlisting and network filtering for AI agents.
Task: 402.1 - Egress Allowlisting & Secret Isolation
"""

from __future__ import annotations

import logging
import ipaddress
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
import re

from django.utils import timezone
from django.db import transaction

from .models import AgentExecution
from .egress_models import EgressRule, EgressRequest

logger = logging.getLogger(__name__)


class EgressService:
    """Service for managing egress allowlisting."""

    def __init__(self) -> None:
        """Initialize egress service."""
        self._default_deny = True  # Default deny all egress

    def check_egress_allowed(
        self,
        destination: str,
        tenant_id: str,
        agent_execution: AgentExecution,
        port: Optional[int] = None,
        protocol: str = "https",
    ) -> tuple[bool, Optional[EgressRule]]:
        """Check if egress to destination is allowed.

        Args:
            destination: Destination (URL, domain, IP, etc.).
            tenant_id: Tenant ID.
            agent_execution: Agent execution instance.
            port: Optional port number.
            protocol: Protocol (http, https, tcp, udp).

        Returns:
            Tuple of (allowed, matched_rule).
        """
        # Get active egress rules for tenant
        rules = EgressRule.objects.filter(
            tenant_id=tenant_id, is_active=True
        )

        # Parse destination
        parsed_dest = self._parse_destination(destination)

        # Check each rule
        for rule in rules:
            if self._match_rule(rule, parsed_dest, port, protocol):
                # Log allowed request
                EgressRequest.objects.create(
                    tenant_id=tenant_id,
                    agent_execution=agent_execution,
                    destination=destination,
                    port=port,
                    protocol=protocol,
                    allowed=True,
                    matched_rule=rule,
                    metadata={"parsed_dest": parsed_dest},
                )

                logger.info(
                    f"Egress allowed: {destination} (matched rule {rule.id})"
                )

                return True, rule

        # Default deny if no rule matches
        EgressRequest.objects.create(
            tenant_id=tenant_id,
            agent_execution=agent_execution,
            destination=destination,
            port=port,
            protocol=protocol,
            allowed=False,
            matched_rule=None,
            metadata={"parsed_dest": parsed_dest},
        )

        logger.warning(f"Egress blocked: {destination} (no matching rule)")

        return False, None

    def create_egress_rule(
        self,
        tenant_id: str,
        name: str,
        destination_type: str,
        destination: str,
        port: Optional[int] = None,
        protocol: str = "https",
        description: str = "",
        created_by: str = "",
    ) -> EgressRule:
        """Create an egress allowlist rule.

        Args:
            tenant_id: Tenant ID.
            name: Rule name.
            destination_type: Type of destination (domain, ip, cidr, url_pattern).
            destination: Destination value.
            port: Optional port number.
            protocol: Protocol (http, https, tcp, udp, all).
            description: Rule description.
            created_by: User who created the rule.

        Returns:
            Created EgressRule instance.

        Raises:
            ValueError: If validation fails.
        """
        # Validate destination type
        valid_types = ["domain", "ip", "cidr", "url_pattern"]
        if destination_type not in valid_types:
            raise ValueError(f"Invalid destination_type: {destination_type}")

        # Validate destination format
        if destination_type == "ip":
            try:
                ipaddress.ip_address(destination)
            except ValueError:
                raise ValueError(f"Invalid IP address: {destination}")

        if destination_type == "cidr":
            try:
                ipaddress.ip_network(destination, strict=False)
            except ValueError:
                raise ValueError(f"Invalid CIDR block: {destination}")

        # Create rule
        rule = EgressRule.objects.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            destination_type=destination_type,
            destination=destination,
            port=port,
            protocol=protocol,
            created_by=created_by,
        )

        logger.info(f"Created egress rule {rule.id} for tenant {tenant_id}")

        return rule

    def list_egress_rules(
        self, tenant_id: str, is_active: Optional[bool] = None
    ) -> List[EgressRule]:
        """List egress rules for tenant.

        Args:
            tenant_id: Tenant ID.
            is_active: Optional active filter.

        Returns:
            List of EgressRule instances.
        """
        query = EgressRule.objects.filter(tenant_id=tenant_id)

        if is_active is not None:
            query = query.filter(is_active=is_active)

        return list(query.order_by("name"))

    def _parse_destination(self, destination: str) -> Dict[str, Any]:
        """Parse destination string.

        Args:
            destination: Destination string.

        Returns:
            Parsed destination dictionary.
        """
        parsed = {
            "original": destination,
            "type": None,
            "domain": None,
            "ip": None,
            "port": None,
            "path": None,
        }

        # Try parsing as URL
        try:
            url = urlparse(destination)
            if url.scheme:
                parsed["type"] = "url"
                parsed["domain"] = url.hostname
                parsed["port"] = url.port
                parsed["path"] = url.path
                return parsed
        except Exception:
            pass

        # Try parsing as IP address
        try:
            ip = ipaddress.ip_address(destination)
            parsed["type"] = "ip"
            parsed["ip"] = str(ip)
            return parsed
        except ValueError:
            pass

        # Try parsing as CIDR
        try:
            network = ipaddress.ip_network(destination, strict=False)
            parsed["type"] = "cidr"
            parsed["ip"] = str(network)
            return parsed
        except ValueError:
            pass

        # Assume domain
        parsed["type"] = "domain"
        parsed["domain"] = destination
        return parsed

    def _match_rule(
        self,
        rule: EgressRule,
        parsed_dest: Dict[str, Any],
        port: Optional[int],
        protocol: str,
    ) -> bool:
        """Check if destination matches rule.

        Args:
            rule: Egress rule.
            parsed_dest: Parsed destination.
            port: Port number.
            protocol: Protocol.

        Returns:
            True if matches, False otherwise.
        """
        # Check protocol
        if rule.protocol != "all" and rule.protocol != protocol:
            return False

        # Check port
        if rule.port is not None and port is not None:
            if rule.port != port:
                return False

        # Match by destination type
        if rule.destination_type == "domain":
            if parsed_dest.get("domain"):
                return self._match_domain(rule.destination, parsed_dest["domain"])
            return False

        elif rule.destination_type == "ip":
            if parsed_dest.get("ip"):
                return rule.destination == parsed_dest["ip"]
            return False

        elif rule.destination_type == "cidr":
            if parsed_dest.get("ip"):
                try:
                    dest_ip = ipaddress.ip_address(parsed_dest["ip"])
                    rule_network = ipaddress.ip_network(rule.destination, strict=False)
                    return dest_ip in rule_network
                except ValueError:
                    return False
            return False

        elif rule.destination_type == "url_pattern":
            if parsed_dest.get("original"):
                try:
                    pattern = re.compile(rule.destination)
                    return pattern.match(parsed_dest["original"]) is not None
                except re.error:
                    return False
            return False

        return False

    def _match_domain(self, rule_domain: str, dest_domain: str) -> bool:
        """Match domain (supports wildcards).

        Args:
            rule_domain: Rule domain pattern.
            dest_domain: Destination domain.

        Returns:
            True if matches, False otherwise.
        """
        # Exact match
        if rule_domain == dest_domain:
            return True

        # Wildcard match (e.g., *.example.com)
        if rule_domain.startswith("*."):
            suffix = rule_domain[2:]
            return dest_domain.endswith("." + suffix) or dest_domain == suffix

        return False


# Global egress service instance
egress_service = EgressService()

