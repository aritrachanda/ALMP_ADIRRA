"""Tests for Phase 0 governance overlay functionality in ElementStateStore.

Description/business-name/metadata are content methods, Postgres-only since Slice F -- they
land wherever ``ADM_DATABASE_URL``/project.yaml already points (this file makes no assumption
about which database that is), so this file cleans up its own test keys before/after each test
to avoid leaving anything behind.
"""
import pytest
from datetime import datetime
from pathlib import Path
from core.element_state import ElementStateStore


@pytest.fixture(autouse=True)
def _clean_rows():
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import ElementDefinition

    def _wipe():
        try:
            with session_scope() as s:
                s.execute(delete(ElementDefinition).where(ElementDefinition.element_key.in_(
                    ["db|public|t|c", "mydb|public|customers|customer_id"])))
        except Exception:
            pass  # Postgres unreachable -- tests below will fail on their own merits

    _wipe()
    yield
    _wipe()


@pytest.fixture
def store(tmp_path):
    """Create a fresh store for each test."""
    store_path = tmp_path / "test_element_states.yaml"
    return ElementStateStore(store_path)


class TestBusinessName:
    """5b.3.2c — business name is a plain value folded into the interpretation set
    (the separate Architect review lifecycle was removed)."""

    def test_setting_a_name_persists_it(self, store):
        assert store.get_business_name("db", "public", "t", "c") is None
        store.set_business_name("db", "public", "t", "c", "Customer Identifier")
        assert store.get_business_name("db", "public", "t", "c") == "Customer Identifier"

    def test_ai_flag_recorded(self, store):
        store.set_business_name("db", "public", "t", "c", "Customer Identifier", is_ai_generated=True)
        meta = store.get_metadata("db", "public", "t", "c")
        assert meta["business_name_is_ai"] is True

    def test_editing_replaces_the_name(self, store):
        store.set_business_name("db", "public", "t", "c", "Customer Identifier")
        store.set_business_name("db", "public", "t", "c", "Client Identifier")
        assert store.get_business_name("db", "public", "t", "c") == "Client Identifier"


class TestElementStateSubmitForReview:
    """Test submit_for_review() method."""

    def test_submit_for_review_sets_submitted_at_and_by(self, store):
        """Test that submit_for_review captures timestamp and actor."""
        # First, create a defined aspect
        store.set("mydb", "public", "customers", "customer_id", "defined")
        store.set_description("mydb", "public", "customers", "customer_id", "Unique customer identifier")
        
        # Then submit for review
        store.submit_for_review("mydb", "public", "customers", "customer_id", submitted_by="alice")
        
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["submitted_by"] == "alice"
        assert status["submitted_at"] is not None
        assert status["decided_at"] is None
        assert status["decision"] is None

    def test_submit_for_review_without_actor(self, store):
        """Test that submit_for_review works with no actor specified."""
        store.set("mydb", "public", "customers", "customer_id", "defined")
        store.submit_for_review("mydb", "public", "customers", "customer_id")
        
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["submitted_at"] is not None
        assert status["submitted_by"] is None

    def test_submit_multiple_times_overwrites(self, store):
        """Test that re-submitting updates the timestamp."""
        store.set("mydb", "public", "customers", "customer_id", "defined")
        
        store.submit_for_review("mydb", "public", "customers", "customer_id", submitted_by="alice")
        first_status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        first_time = first_status["submitted_at"]
        
        # Simulate a delay and resubmit
        store.submit_for_review("mydb", "public", "customers", "customer_id", submitted_by="bob")
        second_status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        
        assert second_status["submitted_by"] == "bob"
        assert second_status["submitted_at"] != first_time  # Should have a new timestamp


class TestElementStateApprove:
    """Test approve() method."""

    def test_approve_sets_decision_and_state(self, store):
        """Test that approve() sets state to approved and records decision."""
        store.set("mydb", "public", "customers", "customer_id", "defined")
        store.submit_for_review("mydb", "public", "customers", "customer_id", submitted_by="alice")
        
        store.approve("mydb", "public", "customers", "customer_id", decided_by="steward")
        
        # Check state changed
        state = store.get("mydb", "public", "customers", "customer_id")
        assert state == "approved"
        
        # Check decision overlay
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["decision"] == "approved"
        assert status["decided_by"] == "steward"
        assert status["decided_at"] is not None
        assert status["reject_reason"] is None

    def test_approve_without_decider(self, store):
        """Test that approve works without specifying the decider."""
        store.set("mydb", "public", "customers", "customer_id", "defined")
        store.approve("mydb", "public", "customers", "customer_id")
        
        state = store.get("mydb", "public", "customers", "customer_id")
        assert state == "approved"

    def test_approve_clears_previous_rejection(self, store):
        """Test that approving after rejection clears the rejection reason."""
        store.set("mydb", "public", "customers", "customer_id", "defined")
        store.submit_for_review("mydb", "public", "customers", "customer_id")
        
        # First reject
        store.reject("mydb", "public", "customers", "customer_id", 
                    decided_by="steward", reason="Too vague")
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["reject_reason"] == "Too vague"
        
        # Then approve (after author fixes)
        store.approve("mydb", "public", "customers", "customer_id", decided_by="steward2")
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["decision"] == "approved"
        assert status["reject_reason"] is None


class TestElementStateReject:
    """Test reject() method."""

    def test_reject_reverts_to_defined_and_records_reason(self, store):
        """Test that reject() reverts state to defined and stores reason."""
        store.set("mydb", "public", "customers", "customer_id", "approved")
        store.submit_for_review("mydb", "public", "customers", "customer_id", submitted_by="alice")
        
        store.reject("mydb", "public", "customers", "customer_id", 
                    decided_by="steward", reason="Definition is ambiguous")
        
        # Check state reverted
        state = store.get("mydb", "public", "customers", "customer_id")
        assert state == "defined"
        
        # Check rejection recorded
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["decision"] == "rejected"
        assert status["decided_by"] == "steward"
        assert status["reject_reason"] == "Definition is ambiguous"
        assert status["decided_at"] is not None

    def test_reject_without_reason(self, store):
        """Test that reject works without a reason."""
        store.set("mydb", "public", "customers", "customer_id", "defined")
        store.reject("mydb", "public", "customers", "customer_id", decided_by="steward")
        
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["decision"] == "rejected"
        assert status["reject_reason"] is None

    def test_reject_allows_resubmission(self, store):
        """Test that after rejection, author can re-edit and resubmit."""
        store.set("mydb", "public", "customers", "customer_id", "defined")
        store.set_description("mydb", "public", "customers", "customer_id", "Original")
        
        store.reject("mydb", "public", "customers", "customer_id", reason="Too vague")
        
        # Author re-edits
        store.set_description("mydb", "public", "customers", "customer_id", "Improved description")
        
        # Author resubmits
        store.submit_for_review("mydb", "public", "customers", "customer_id", submitted_by="alice")
        
        # New submission should be recorded
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["submitted_by"] == "alice"
        # The new submitted_at should be after the decision time
        assert status["submitted_at"] > status["decided_at"]


class TestElementStateGetSubmissionStatus:
    """Test get_submission_status() method."""

    def test_get_submission_status_returns_empty_dict_for_new_element(self, store):
        """Test that new elements return all-None status."""
        store.set("mydb", "public", "customers", "customer_id", "draft")
        
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["submitted_at"] is None
        assert status["submitted_by"] is None
        assert status["decided_at"] is None
        assert status["decided_by"] is None
        assert status["decision"] is None
        assert status["reject_reason"] is None

    def test_get_submission_status_for_nonexistent_element(self, store):
        """Test that querying non-existent element returns all-None status."""
        status = store.get_submission_status("unknown", "schema", "table", "column")
        assert all(v is None for v in status.values())


class TestElementStateBackwardCompatibility:
    """Test that Phase 0 doesn't break existing operations."""

    def test_existing_set_and_get_unchanged(self, store):
        """Test that existing state operations still work."""
        store.set("mydb", "public", "customers", "customer_id", "draft")
        state = store.get("mydb", "public", "customers", "customer_id")
        assert state == "draft"
        
        store.set("mydb", "public", "customers", "customer_id", "defined")
        state = store.get("mydb", "public", "customers", "customer_id")
        assert state == "defined"

    def test_existing_description_operations_unchanged(self, store):
        """Test that description operations still work."""
        desc = "Unique customer ID"
        store.set_description("mydb", "public", "customers", "customer_id", desc)
        retrieved = store.get_description("mydb", "public", "customers", "customer_id")
        assert retrieved == desc

    def test_existing_business_name_operations_unchanged(self, store):
        """Test that business name operations still work."""
        name = "Customer Identifier"
        store.set_business_name("mydb", "public", "customers", "customer_id", name)
        retrieved = store.get_business_name("mydb", "public", "customers", "customer_id")
        assert retrieved == name

    def test_metadata_preserved_across_submission_workflow(self, store):
        """Test that metadata is preserved when using new submission methods."""
        # Create element with metadata
        store.set("mydb", "public", "customers", "customer_id", "draft")
        store.set_description("mydb", "public", "customers", "customer_id", "Primary key")
        store.set_metadata("mydb", "public", "customers", "customer_id", 
                          {"is_ai_generated": True})
        
        # Use new submission methods
        store.submit_for_review("mydb", "public", "customers", "customer_id")
        store.approve("mydb", "public", "customers", "customer_id")
        
        # Verify metadata still there
        meta = store.get_metadata("mydb", "public", "customers", "customer_id")
        assert meta.get("is_ai_generated") is True
        
        # Verify description still there
        desc = store.get_description("mydb", "public", "customers", "customer_id")
        assert desc == "Primary key"


class TestElementStateWorkflow:
    """Test end-to-end workflow scenarios."""

    def test_complete_governance_workflow(self, store):
        """Test a realistic governance workflow from draft to approval."""
        # 1. Author creates draft with description
        store.set("mydb", "public", "customers", "customer_id", "draft")
        store.set_description("mydb", "public", "customers", "customer_id", 
                             "Unique identifier for a customer in the system")
        
        # 2. Author completes it and marks as defined
        store.set("mydb", "public", "customers", "customer_id", "defined")
        
        # 3. Author submits for review
        store.submit_for_review("mydb", "public", "customers", "customer_id", 
                               submitted_by="alice")
        
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["submitted_by"] == "alice"
        assert status["decision"] is None
        
        # 4. Steward reviews and approves
        store.approve("mydb", "public", "customers", "customer_id", decided_by="steward_bob")
        
        state = store.get("mydb", "public", "customers", "customer_id")
        assert state == "approved"
        
        status = store.get_submission_status("mydb", "public", "customers", "customer_id")
        assert status["decided_by"] == "steward_bob"
        assert status["decision"] == "approved"

    def test_rejection_and_resubmission_workflow(self, store):
        """Test workflow where submission is rejected, then resubmitted."""
        # Create and submit
        store.set("mydb", "public", "customers", "customer_id", "defined")
        store.set_description("mydb", "public", "customers", "customer_id", "ID")
        store.submit_for_review("mydb", "public", "customers", "customer_id", 
                               submitted_by="alice")
        
        # Reject
        store.reject("mydb", "public", "customers", "customer_id", 
                    decided_by="steward", reason="Too minimal, needs more detail")
        
        state = store.get("mydb", "public", "customers", "customer_id")
        assert state == "defined"  # Reverted so author can edit
        
        # Author improves
        store.set_description("mydb", "public", "customers", "customer_id", 
                             "Unique identifier for a customer in the system")
        
        # Resubmit
        store.submit_for_review("mydb", "public", "customers", "customer_id", 
                               submitted_by="alice")
        
        # This time approve
        store.approve("mydb", "public", "customers", "customer_id", decided_by="steward")
        
        state = store.get("mydb", "public", "customers", "customer_id")
        assert state == "approved"
