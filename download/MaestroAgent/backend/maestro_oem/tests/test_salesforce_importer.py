"""Tests for the Salesforce CRM importer — real OAuth integration scaffold.

Verifies that the SalesforcePageFetcher:
  1. Implements the PageFetcher interface (same as GitHub/Slack/Jira)
  2. Normalizes Salesforce records into customer event-dicts correctly
  3. Is registered in the ProviderFactory
  4. Maps Opportunity/Task/Event/Case/Contract to the right customer signal types

These tests use synthetic Salesforce records (no real API calls) to verify
the normalization logic. A real integration test would require Salesforce
credentials and is out of scope for the unit test suite.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from maestro_oem.importers.salesforce_importer import SalesforcePageFetcher
from maestro_oem.importers.factory import ProviderFactory, _FETCHER_CLASSES
from maestro_oem.ingestion import PageFetcher
from maestro_oem.providers.customer import normalize_customer
from maestro_oem.signal import SignalProvider, SignalType


class TestSalesforceImporterRegistration:
    def test_salesforce_fetcher_registered_in_factory(self):
        """The SalesforcePageFetcher must be registered for the 'customer' provider."""
        assert "customer" in _FETCHER_CLASSES
        assert _FETCHER_CLASSES["customer"] is SalesforcePageFetcher

    def test_factory_creates_salesforce_fetcher(self):
        """ProviderFactory.create('customer') returns a SalesforcePageFetcher."""
        from maestro_oem.oauth_manager import OAuthManager
        from maestro_oem.checkpoint_store import CheckpointStore
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = CheckpointStore(db_path)
            oauth = OAuthManager(store)
            factory = ProviderFactory(oauth)
            fetcher = factory.create("customer", org_id="https://acme.my.salesforce.com")
            assert isinstance(fetcher, SalesforcePageFetcher)
            assert fetcher.provider == "customer"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_salesforce_fetcher_implements_page_fetcher(self):
        """SalesforcePageFetcher must satisfy the PageFetcher interface."""
        from maestro_oem.oauth_manager import OAuthManager
        from maestro_oem.checkpoint_store import CheckpointStore
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = CheckpointStore(db_path)
            oauth = OAuthManager(store)
            fetcher = SalesforcePageFetcher(oauth, org_id="https://test.my.salesforce.com")
            assert isinstance(fetcher, PageFetcher)
            assert fetcher.provider == "customer"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_customer_provider_in_supported_list(self):
        """The factory lists 'customer' as a supported provider."""
        from maestro_oem.oauth_manager import OAuthManager
        from maestro_oem.checkpoint_store import CheckpointStore
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = CheckpointStore(db_path)
            oauth = OAuthManager(store)
            factory = ProviderFactory(oauth)
            assert "customer" in factory.supported_providers()
            assert factory.is_supported("customer")
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestSalesforceNormalization:
    """Verify that Salesforce records map to the right customer event types."""

    def _make_fetcher(self):
        from maestro_oem.oauth_manager import OAuthManager
        from maestro_oem.checkpoint_store import CheckpointStore
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        store = CheckpointStore(db_path)
        oauth = OAuthManager(store)
        return SalesforcePageFetcher(oauth, org_id="https://test.my.salesforce.com")

    def test_opportunity_won_maps_to_decision_renewed(self):
        """A Closed Won opportunity becomes a customer.decision signal with outcome=renewed."""
        fetcher = self._make_fetcher()
        record = {
            "attributes": {"type": "Opportunity"},
            "Id": "006000000000001",
            "Name": "Globex Renewal",
            "StageName": "Closed Won",
            "Amount": 3200000,
            "LastModifiedDate": "2025-01-05T10:00:00Z",
            "Account": {"Name": "Globex"},
            "Owner": {"Email": "jane.d@acme.com"},
            "Who": {"Email": "raj@globex.com"},
        }
        event = fetcher.normalize_item(record)
        assert event["event_type"] == "decision"
        assert event["metadata"]["customer"] == "Globex"
        assert event["metadata"]["arr_impact"] == 3200000.0
        assert event["metadata"]["decision_outcome"] == "renewed"
        # Verify the event normalizes to a proper ExecutionSignal
        sig = normalize_customer(event)
        assert sig.type == SignalType.CUSTOMER_DECISION
        assert sig.provider == SignalProvider.CUSTOMER

    def test_opportunity_lost_maps_to_decision_churned(self):
        """A Closed Lost opportunity becomes a customer.decision with outcome=churned."""
        fetcher = self._make_fetcher()
        record = {
            "attributes": {"type": "Opportunity"},
            "Id": "006000000000002",
            "Name": "Hooli Renewal",
            "StageName": "Closed Lost",
            "Amount": 2400000,
            "LastModifiedDate": "2024-11-10T10:00:00Z",
            "Account": {"Name": "Hooli"},
            "Owner": {"Email": "jane.d@acme.com"},
            "Who": {"Email": "vincent@hooli.com"},
        }
        event = fetcher.normalize_item(record)
        assert event["event_type"] == "decision"
        assert event["metadata"]["decision_outcome"] == "churned"
        assert event["metadata"]["arr_impact"] == 2400000.0

    def test_opportunity_in_progress_maps_to_stage_change(self):
        """An open opportunity becomes a customer.stage_change signal."""
        fetcher = self._make_fetcher()
        record = {
            "attributes": {"type": "Opportunity"},
            "Id": "006000000000003",
            "Name": "Initech Pilot",
            "StageName": "Negotiation",
            "Amount": 1800000,
            "LastModifiedDate": "2024-12-15T12:00:00Z",
            "Account": {"Name": "Initech"},
            "Owner": {"Email": "jane.d@acme.com"},
            "Who": {"Email": "priya@initech.com"},
        }
        event = fetcher.normalize_item(record)
        assert event["event_type"] == "stage_change"
        assert event["metadata"]["stage"] == "negotiation"

    def test_task_meeting_maps_to_meeting_event(self):
        """A Salesforce Task with TaskSubtype='meeting' becomes a customer.meeting."""
        fetcher = self._make_fetcher()
        record = {
            "attributes": {"type": "Task"},
            "Id": "00T000000000001",
            "Subject": "Q4 renewal kickoff",
            "TaskSubtype": "Meeting",
            "ActivityDate": "2024-10-15",
            "Account": {"Name": "Globex"},
            "Owner": {"Email": "jane.d@acme.com"},
            "Who": {"Email": "raj@globex.com"},
        }
        event = fetcher.normalize_item(record)
        assert event["event_type"] == "meeting"
        assert event["metadata"]["customer"] == "Globex"
        assert event["metadata"]["contact"] == "raj@globex.com"
        assert "raj@globex.com" in event["metadata"]["participants"]

    def test_task_email_maps_to_email_event(self):
        """A Salesforce Task with TaskSubtype='email' becomes a customer.email."""
        fetcher = self._make_fetcher()
        record = {
            "attributes": {"type": "Task"},
            "Id": "00T000000000002",
            "Subject": "Re: pricing",
            "TaskSubtype": "Email",
            "ActivityDate": "2024-11-20",
            "Account": {"Name": "Initech"},
            "Owner": {"Email": "jane.d@acme.com"},
            "Who": {"Email": "max@initech.com"},
        }
        event = fetcher.normalize_item(record)
        assert event["event_type"] == "email"

    def test_case_maps_to_support_ticket(self):
        """A Salesforce Case becomes a customer.support_ticket signal."""
        fetcher = self._make_fetcher()
        record = {
            "attributes": {"type": "Case"},
            "Id": "500000000000001",
            "CaseNumber": "00001001",
            "Subject": "Login failure",
            "Status": "Open",
            "Priority": "High",
            "CreatedDate": "2024-12-01T09:00:00Z",
            "Account": {"Name": "Globex"},
            "Owner": {"Email": "support@acme.com"},
            "Who": {"Email": "raj@globex.com"},
        }
        event = fetcher.normalize_item(record)
        assert event["event_type"] == "support_ticket"
        assert event["metadata"]["ticket_id"] == "00001001"
        sig = normalize_customer(event)
        assert sig.type == SignalType.CUSTOMER_SUPPORT_TICKET

    def test_contract_activated_maps_to_contract_signed(self):
        """A Salesforce Contract with Status='Activated' becomes contract_signed."""
        fetcher = self._make_fetcher()
        record = {
            "attributes": {"type": "Contract"},
            "Id": "800000000000001",
            "ContractNumber": "00000001",
            "Status": "Activated",
            "StartDate": "2025-01-01",
            "EndDate": "2026-01-01",
            "LastModifiedDate": "2025-01-05T10:00:00Z",
            "Account": {"Name": "Globex"},
            "Owner": {"Email": "jane.d@acme.com"},
            "Who": {"Email": "sam@globex.com"},
        }
        event = fetcher.normalize_item(record)
        assert event["event_type"] == "contract_signed"
        sig = normalize_customer(event)
        assert sig.type == SignalType.CUSTOMER_CONTRACT_SIGNED

    def test_contract_cancelled_maps_to_contract_churned(self):
        """A Salesforce Contract with Status='Cancelled' becomes contract_churned."""
        fetcher = self._make_fetcher()
        record = {
            "attributes": {"type": "Contract"},
            "Id": "800000000000002",
            "ContractNumber": "00000002",
            "Status": "Cancelled",
            "LastModifiedDate": "2024-11-10T10:00:00Z",
            "Account": {"Name": "Hooli"},
            "Owner": {"Email": "jane.d@acme.com"},
            "Who": {"Email": "vincent@hooli.com"},
        }
        event = fetcher.normalize_item(record)
        assert event["event_type"] == "contract_churned"
        sig = normalize_customer(event)
        assert sig.type == SignalType.CUSTOMER_CONTRACT_CHURNED


class TestSalesforceEndToEndNormalization:
    """Verify that Salesforce records flow through the full pipeline:
    record → normalize_item → normalize_customer → ExecutionSignal
    """

    def test_full_pipeline_opportunity_to_signal(self):
        """A Salesforce Opportunity record becomes a proper ExecutionSignal."""
        from maestro_oem.oauth_manager import OAuthManager
        from maestro_oem.checkpoint_store import CheckpointStore
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = CheckpointStore(db_path)
            oauth = OAuthManager(store)
            fetcher = SalesforcePageFetcher(oauth, org_id="https://test.my.salesforce.com")
            record = {
                "attributes": {"type": "Opportunity"},
                "Id": "006000000000001",
                "Name": "Globex Renewal",
                "StageName": "Closed Won",
                "Amount": 3200000,
                "LastModifiedDate": "2025-01-05T10:00:00Z",
                "Account": {"Name": "Globex"},
                "Owner": {"Email": "jane.d@acme.com"},
                "Who": {"Email": "raj@globex.com"},
            }
            event = fetcher.normalize_item(record)
            sig = normalize_customer(event)
            assert sig.provider == SignalProvider.CUSTOMER
            assert sig.type == SignalType.CUSTOMER_DECISION
            assert sig.metadata["customer"] == "Globex"
            assert sig.metadata["arr_impact"] == 3200000.0
            assert sig.metadata["decision_outcome"] == "renewed"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
