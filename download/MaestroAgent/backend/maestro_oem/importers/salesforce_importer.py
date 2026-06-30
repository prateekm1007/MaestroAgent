"""Salesforce CRM historical importer.

Fetches:
  - Opportunities (pipeline stage history, amounts, close dates)
  - Tasks (meetings, calls, emails logged in CRM)
  - Events (calendar items synced to Salesforce)
  - Cases (support tickets)
  - Contracts (signed/renewed/churned milestones)

Pagination:
  - Salesforce REST API uses nextRecordsUrl for pagination
  - Page size: 200 (SOQL LIMIT)
  - Query: SELECT ... FROM Opportunity WHERE LastModifiedDate >= :since

Rate limits:
  - 100k req/day per licensed user
  - No X-RateLimit headers; throttled via 503 responses

OAuth scopes (Salesforce Connected App):
  - api (full API access)
  - refresh_token (offline access)
  - web (web server flow)

The fetcher normalizes Salesforce records into the customer event-dict
format that normalize_customer() expects. This means CRM data flows
through the SAME ingestion pipeline as the demo provider and every
other signal source — no parallel intelligence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

from maestro_oem.importers.base import BaseProviderFetcher
from maestro_oem.ingestion import PageResult, PageStatus

logger = logging.getLogger(__name__)


class SalesforcePageFetcher(BaseProviderFetcher):
    """Fetches Salesforce opportunities, tasks, events, cases, and contracts.

    org_id is the Salesforce instance URL (e.g. "https://acme.my.salesforce.com").
    The OAuth token must have 'api' scope.
    """

    provider = "customer"  # Maps to the Customer Judgment Engine provider
    base_url = ""  # Set per-instance from org_id
    page_size = 200

    # SOQL queries for each resource type. :since is bound to the last sync time.
    _QUERIES = {
        "opportunity": (
            "SELECT Id, Name, StageName, Amount, CloseDate, LastModifiedDate, "
            "AccountId, Account.Name, OwnerId, Owner.Email "
            "FROM Opportunity WHERE LastModifiedDate >= {since} "
            "ORDER BY LastModifiedDate LIMIT {limit}"
        ),
        "task": (
            "SELECT Id, Subject, Status, Priority, ActivityDate, TaskSubtype, "
            "WhoId, Who.Email, WhatId, AccountId, Account.Name, OwnerId, Owner.Email "
            "FROM Task WHERE LastModifiedDate >= {since} "
            "ORDER BY LastModifiedDate LIMIT {limit}"
        ),
        "event": (
            "SELECT Id, Subject, StartDateTime, EndDateTime, DurationInMinutes, "
            "WhoId, Who.Email, WhatId, AccountId, Account.Name, OwnerId, Owner.Email "
            "FROM Event WHERE LastModifiedDate >= {since} "
            "ORDER BY LastModifiedDate LIMIT {limit}"
        ),
        "case": (
            "SELECT Id, CaseNumber, Subject, Status, Priority, Origin, "
            "AccountId, Account.Name, OwnerId, Owner.Email, CreatedDate "
            "FROM Case WHERE LastModifiedDate >= {since} "
            "ORDER BY LastModifiedDate LIMIT {limit}"
        ),
        "contract": (
            "SELECT Id, ContractNumber, Status, StartDate, EndDate, "
            "AccountId, Account.Name, OwnerId, Owner.Email "
            "FROM Contract WHERE LastModifiedDate >= {since} "
            "ORDER BY LastModifiedDate LIMIT {limit}"
        ),
    }

    def __init__(
        self,
        oauth,
        http_client: httpx.AsyncClient | None = None,
        page_size: int | None = None,
        org_id: str | None = None,
    ) -> None:
        super().__init__(oauth, http_client, page_size, org_id)
        if org_id:
            # org_id is the Salesforce instance URL
            self.base_url = org_id.rstrip("/") + "/"
        else:
            self.base_url = "https://login.salesforce.com/"

    async def fetch_page(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        """Fetch one page of Salesforce records.

        cursor is the nextRecordsUrl from the previous page (Salesforce's
        pagination mechanism). On page 1, we issue the initial SOQL query.
        """
        since_str = (since or datetime(2000, 1, 1, tzinfo=timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            if cursor:
                # Continue from the previous page's nextRecordsUrl
                url = urljoin(self.base_url, cursor)
            else:
                # First page — issue the SOQL query for each resource type.
                # We cycle through resource types across pages, starting with
                # opportunity. A full sync fetches all 5 types sequentially.
                resource_types = list(self._QUERIES.keys())
                resource = resource_types[(page - 1) % len(resource_types)]
                soql = self._QUERIES[resource].format(
                    since=since_str,
                    limit=self.page_size,
                )
                url = urljoin(self.base_url, f"/services/data/v58.0/query/?q={soql}")

            resp = await self._request("GET", url)

            if resp.status_code == 200:
                data = resp.json()
                items = [self.normalize_item(record) for record in data.get("records", [])]
                next_cursor = data.get("nextRecordsUrl", "") if not data.get("done", True) else ""
                return PageResult(
                    page_number=page,
                    status=PageStatus.SUCCESS,
                    items=items,
                    items_count=len(items),
                    next_page=page + 1 if next_cursor else None,
                    next_cursor=next_cursor,
                    rate_limit_remaining=99999,  # Salesforce doesn't expose this
                )
            elif resp.status_code == 401:
                return self._auth_expired_result(page)
            elif resp.status_code == 503:
                return self._rate_limited_result(resp, page)
            else:
                return self._error_result(page, f"Salesforce API {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            logger.exception("Salesforce fetch failed")
            return self._error_result(page, str(e))

    async def estimate_total_pages(self, since: datetime | None = None) -> int:
        """Estimate total pages by querying COUNT() for each resource type."""
        since_str = (since or datetime(2000, 1, 1, tzinfo=timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
        total_records = 0
        for resource, query_template in self._QUERIES.items():
            count_query = query_template.split("FROM")[0].replace("SELECT", "SELECT COUNT()")
            count_query = f"SELECT COUNT() FROM {query_template.split('FROM')[1].split('WHERE')[0]} WHERE LastModifiedDate >= {since_str}"
            try:
                resp = await self._request("GET", urljoin(self.base_url, f"/services/data/v58.0/query/?q={count_query}"))
                if resp.status_code == 200:
                    total_records += resp.json().get("totalSize", 0)
            except Exception:
                pass
        return max(1, (total_records + self.page_size - 1) // self.page_size)

    def normalize_item(self, record: dict[str, Any]) -> dict[str, Any]:
        """Normalize a Salesforce record into a customer event-dict.

        Maps Salesforce sObjects (Opportunity, Task, Event, Case, Contract)
        to the customer event types that normalize_customer() expects.
        """
        # Determine the Salesforce object type from the record's attributes
        attrs = record.get("attributes", {})
        sobject_type = attrs.get("type", "")

        account = record.get("Account", {})
        customer_name = account.get("Name", record.get("AccountId", "unknown"))
        owner = record.get("Owner", {})
        actor_email = owner.get("Email", "unknown@salesforce.com")

        if sobject_type == "Opportunity":
            return self._normalize_opportunity(record, customer_name, actor_email)
        elif sobject_type == "Task":
            return self._normalize_task(record, customer_name, actor_email)
        elif sobject_type == "Event":
            return self._normalize_event(record, customer_name, actor_email)
        elif sobject_type == "Case":
            return self._normalize_case(record, customer_name, actor_email)
        elif sobject_type == "Contract":
            return self._normalize_contract(record, customer_name, actor_email)

        # Unknown type — return a generic meeting event
        return {
            "event_type": "meeting",
            "actor": actor_email,
            "artifact": f"salesforce:{record.get('Id', '')}",
            "timestamp": record.get("LastModifiedDate", datetime.now(timezone.utc).isoformat()),
            "metadata": {
                "customer": customer_name,
                "contact": record.get("Who", {}).get("Email", ""),
                "role": "",
                "arr_impact": 0,
            },
        }

    def _normalize_opportunity(self, record, customer, actor):
        """Opportunity → stage_change or decision event."""
        stage = record.get("StageName", "").lower()
        amount = float(record.get("Amount", 0) or 0)
        # Closed Won → decision (renewed/signed); Closed Lost → decision (churned)
        if "won" in stage:
            return {
                "event_type": "decision",
                "actor": actor,
                "artifact": f"salesforce:opp:{record.get('Id', '')}",
                "timestamp": record.get("LastModifiedDate", datetime.now(timezone.utc).isoformat()),
                "metadata": {
                    "customer": customer,
                    "contact": record.get("Who", {}).get("Email", ""),
                    "role": "economic_buyer",
                    "arr_impact": amount,
                    "decision_outcome": "renewed" if amount > 0 else "signed",
                },
            }
        if "lost" in stage:
            return {
                "event_type": "decision",
                "actor": actor,
                "artifact": f"salesforce:opp:{record.get('Id', '')}",
                "timestamp": record.get("LastModifiedDate", datetime.now(timezone.utc).isoformat()),
                "metadata": {
                    "customer": customer,
                    "contact": record.get("Who", {}).get("Email", ""),
                    "role": "economic_buyer",
                    "arr_impact": amount,
                    "decision_outcome": "churned",
                },
            }
        # Stage change (not closed)
        return {
            "event_type": "stage_change",
            "actor": actor,
            "artifact": f"salesforce:opp:{record.get('Id', '')}",
            "timestamp": record.get("LastModifiedDate", datetime.now(timezone.utc).isoformat()),
            "metadata": {
                "customer": customer,
                "contact": record.get("Who", {}).get("Email", ""),
                "role": "champion",
                "arr_impact": amount,
                "stage": stage,
            },
        }

    def _normalize_task(self, record, customer, actor):
        """Task → meeting/email/call event based on TaskSubtype."""
        subtype = record.get("TaskSubtype", "call").lower()
        event_type_map = {
            "call": "meeting",
            "email": "email",
            "meeting": "meeting",
        }
        event_type = event_type_map.get(subtype, "meeting")
        who = record.get("Who", {})
        return {
            "event_type": event_type,
            "actor": actor,
            "artifact": f"salesforce:task:{record.get('Id', '')}",
            "timestamp": record.get("ActivityDate", record.get("LastModifiedDate", datetime.now(timezone.utc).isoformat())),
            "metadata": {
                "customer": customer,
                "contact": who.get("Email", ""),
                "role": "champion",
                "arr_impact": 0,
                "subject": record.get("Subject", ""),
                "participants": [actor, who.get("Email", "")],
            },
        }

    def _normalize_event(self, record, customer, actor):
        """Event → meeting event."""
        who = record.get("Who", {})
        duration = record.get("DurationInMinutes", 0)
        return {
            "event_type": "meeting",
            "actor": actor,
            "artifact": f"salesforce:event:{record.get('Id', '')}",
            "timestamp": record.get("StartDateTime", datetime.now(timezone.utc).isoformat()),
            "metadata": {
                "customer": customer,
                "contact": who.get("Email", ""),
                "role": "champion",
                "arr_impact": 0,
                "subject": record.get("Subject", ""),
                "duration": duration,
                "participants": [actor, who.get("Email", "")],
            },
        }

    def _normalize_case(self, record, customer, actor):
        """Case → support_ticket event."""
        return {
            "event_type": "support_ticket",
            "actor": actor,
            "artifact": f"salesforce:case:{record.get('Id', '')}",
            "timestamp": record.get("CreatedDate", datetime.now(timezone.utc).isoformat()),
            "metadata": {
                "customer": customer,
                "contact": record.get("Who", {}).get("Email", ""),
                "role": "champion",
                "arr_impact": 0,
                "ticket_id": record.get("CaseNumber", ""),
                "subject": record.get("Subject", ""),
            },
        }

    def _normalize_contract(self, record, customer, actor):
        """Contract → contract_signed/renewed/churned based on Status."""
        status = record.get("Status", "").lower()
        if status in ("activated", "signed"):
            event_type = "contract_signed"
        elif status in ("renewed", "renewing"):
            event_type = "contract_renewed"
        elif status in ("cancelled", "expired", "terminated"):
            event_type = "contract_churned"
        else:
            event_type = "contract_signed"
        return {
            "event_type": event_type,
            "actor": actor,
            "artifact": f"salesforce:contract:{record.get('Id', '')}",
            "timestamp": record.get("LastModifiedDate", datetime.now(timezone.utc).isoformat()),
            "metadata": {
                "customer": customer,
                "contact": record.get("Who", {}).get("Email", ""),
                "role": "economic_buyer",
                "arr_impact": 0,
                "contract_value": 0,
            },
        }
