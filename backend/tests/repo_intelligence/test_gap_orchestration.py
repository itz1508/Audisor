"""Tests for gap analysis orchestration.

Comprehensive tests for the gap analysis system.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from audisor.repo_intelligence.gap_models import (
    GapCategory,
    GapFinding,
    GapLevel,
    GapSeverity,
    GapStatus,
    TriggerDigest,
    TriggerType,
    EvidenceLocation,
)
from audisor.repo_intelligence.gap_analysis import (
    find_gap,
    generate_gap_id,
    generate_gap_run_id,
    compute_file_hash,
)
from audisor.repo_intelligence.gap_triggers import (
    compute_trigger_digest,
    should_trigger_gap,
    trigger_gap_run,
    TriggerConfig,
)
from audisor.repo_intelligence.gap_records import get_gap_record
from audisor.repo_intelligence.completion_analysis import analyze_completion
from audisor.repo_intelligence.gap_analysis import (
    ANALYSIS_COMPLETE,
    EVIDENCE_INCOMPLETE,
)


# ============== Gap Models Tests ==============


class TestGapModels:
    """Test gap analysis data models."""

    def test_gap_finding_as_dict(self):
        """GapFinding serializes to dict correctly."""
        finding = GapFinding(
            gap_id="gap-123",
            category=GapCategory.IMPLEMENTATION,
            severity=GapSeverity.HIGH,
            expected_claim="Function should exist",
            observed_state="Function is missing",
            evidence_locations=[
                EvidenceLocation(path="module.py", line=10)
            ],
            affected_paths=["module.py"],
            required_correction="Add function",
            required_validation="Test function exists",
            confidence=0.95,
        )
        
        d = finding.as_dict()
        assert d["gap_id"] == "gap-123"
        assert d["category"] == "implementation"
        assert d["severity"] == "high"
        assert d["confidence"] == 0.95

    def test_trigger_digest_computation(self):
        """TriggerDigest computes deterministic digest."""
        digest1 = TriggerDigest(
            task_digest="task-1",
            trigger_type=TriggerType.FILE_APPLIED,
            repository_head="abc123",
        )
        digest2 = TriggerDigest(
            task_digest="task-1",
            trigger_type=TriggerType.FILE_APPLIED,
            repository_head="abc123",
        )
        
        assert digest1.compute_digest() == digest2.compute_digest()

    def test_trigger_digest_changes_with_input(self):
        """TriggerDigest changes when input changes."""
        digest1 = TriggerDigest(
            task_digest="task-1",
            trigger_type=TriggerType.FILE_APPLIED,
        )
        digest2 = TriggerDigest(
            task_digest="task-2",
            trigger_type=TriggerType.FILE_APPLIED,
        )
        
        assert digest1.compute_digest() != digest2.compute_digest()


# ============== Gap Analysis Tests ==============


class TestGapAnalysis:
    """Test gap analysis engine."""

    def test_generate_gap_id(self):
        """generate_gap_id produces unique IDs."""
        id1 = generate_gap_id()
        id2 = generate_gap_id()
        assert id1 != id2
        assert id1.startswith("gap-")

    def test_generate_gap_run_id(self):
        """generate_gap_run_id produces unique IDs."""
        id1 = generate_gap_run_id()
        id2 = generate_gap_run_id()
        assert id1 != id2
        assert id1.startswith("gaprun-")

    def test_compute_file_hash(self, tmp_path):
        """compute_file_hash produces deterministic hash."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content")
        
        file2 = tmp_path / "file2.txt"
        file2.write_text("content")
        
        assert compute_file_hash(file1) == compute_file_hash(file2)

    def test_compute_file_hash_missing(self, tmp_path):
        """compute_file_hash returns 'missing' for non-existent file."""
        missing = tmp_path / "missing.txt"
        assert compute_file_hash(missing) == "missing"

    def test_find_gap_basic(self, tmp_path):
        """find_gap performs basic gap analysis."""
        # Create a simple file
        (tmp_path / "module.py").write_text("def hello(): pass")
        
        result = find_gap(
            repository_root=tmp_path,
            trigger_type=TriggerType.FILE_APPLIED,
            trigger_level=GapLevel.INCREMENTAL,
            changed_paths=["module.py"],
        )
        
        assert result["status"] == "success"
        assert "gap_run_id" in result["result"]
        assert result["result"]["trigger_type"] == "file_applied"

    def test_find_gap_with_missing_file(self, tmp_path):
        """find_gap detects missing files."""
        result = find_gap(
            repository_root=tmp_path,
            trigger_type=TriggerType.FILE_APPLIED,
            trigger_level=GapLevel.INCREMENTAL,
            changed_paths=["missing.py"],
        )
        
        assert result["status"] == "success"
        # Should have a finding for the missing file
        findings = result["result"]["findings"]
        assert len(findings) > 0


# ============== Gap Trigger Tests ==============


class TestGapTriggers:
    """Test automatic gap trigger system."""

    def test_should_trigger_gap_enabled(self):
        """should_trigger_gap returns True when enabled."""
        config = TriggerConfig(auto_enabled=True)
        assert should_trigger_gap(TriggerType.FILE_APPLIED, config) is True

    def test_should_trigger_gap_disabled(self):
        """should_trigger_gap returns False when disabled."""
        config = TriggerConfig(auto_enabled=False)
        assert should_trigger_gap(TriggerType.FILE_APPLIED, config) is False

    def test_should_trigger_gap_on_failure(self):
        """Non-apply triggers never auto-fire in the backend (decision 5)."""
        config = TriggerConfig(auto_enabled=False)
        assert should_trigger_gap(TriggerType.EXECUTION_FAILURE, config) is False
        # Even when enabled: failure triggers belong to the runtime/harness,
        # only FILE_APPLIED/CHANGESET_APPLIED auto-fire in the backend.
        config.auto_enabled = True
        assert should_trigger_gap(TriggerType.EXECUTION_FAILURE, config) is False
        assert should_trigger_gap(TriggerType.CHANGESET_APPLIED, config) is True

    def test_compute_trigger_digest_deterministic(self, tmp_path):
        """compute_trigger_digest is deterministic."""
        (tmp_path / "file.py").write_text("content")
        
        digest1 = compute_trigger_digest(
            task_id="task-1",
            plan_id=None,
            trigger_type=TriggerType.FILE_APPLIED,
            repository_head="abc123",
            changed_paths=["file.py"],
            repository_root=tmp_path,
        )
        
        digest2 = compute_trigger_digest(
            task_id="task-1",
            plan_id=None,
            trigger_type=TriggerType.FILE_APPLIED,
            repository_head="abc123",
            changed_paths=["file.py"],
            repository_root=tmp_path,
        )
        
        assert digest1 == digest2

    def test_compute_trigger_digest_changes_with_content(self, tmp_path):
        """compute_trigger_digest changes when file content changes."""
        (tmp_path / "file.py").write_text("content1")
        
        digest1 = compute_trigger_digest(
            task_id="task-1",
            plan_id=None,
            trigger_type=TriggerType.FILE_APPLIED,
            repository_head="abc123",
            changed_paths=["file.py"],
            repository_root=tmp_path,
        )
        
        (tmp_path / "file.py").write_text("content2")
        
        digest2 = compute_trigger_digest(
            task_id="task-1",
            plan_id=None,
            trigger_type=TriggerType.FILE_APPLIED,
            repository_head="abc123",
            changed_paths=["file.py"],
            repository_root=tmp_path,
        )
        
        assert digest1 != digest2


# ============== Analysis Status / Persistence Tests ==============


class TestAnalysisStatus:
    """Placeholder analysis levels must report evidence_incomplete (decision 9)."""

    def test_incremental_analysis_is_complete(self, tmp_path):
        (tmp_path / "module.py").write_text("def hello(): pass")
        result = find_gap(
            repository_root=tmp_path,
            trigger_type=TriggerType.FILE_APPLIED,
            trigger_level=GapLevel.INCREMENTAL,
            changed_paths=["module.py"],
        )
        assert result["status"] == "success"
        assert result["result"]["analysis_status"] == ANALYSIS_COMPLETE
        assert result["result"]["no_material_gap"] is True

    def test_completion_analysis_reports_evidence_incomplete(self, tmp_path):
        result = find_gap(
            repository_root=tmp_path,
            trigger_type=TriggerType.IMPLEMENTATION_COMPLETE,
            trigger_level=GapLevel.COMPLETION,
            success_definition="all tests pass",
        )
        assert result["status"] == "success"
        assert result["result"]["analysis_status"] == EVIDENCE_INCOMPLETE
        # The placeholder must never claim proof of absence of gaps.
        assert result["result"]["no_material_gap"] is False

    def test_diagnostic_analysis_reports_evidence_incomplete(self, tmp_path):
        result = find_gap(
            repository_root=tmp_path,
            trigger_type=TriggerType.EXECUTION_FAILURE,
            trigger_level=GapLevel.DIAGNOSTIC,
        )
        assert result["status"] == "success"
        assert result["result"]["analysis_status"] == EVIDENCE_INCOMPLETE
        assert result["result"]["no_material_gap"] is False


class TestTriggerPersistence:
    """trigger_gap_run persists every live finding (decision 10)."""

    def test_trigger_persists_all_findings(self, tmp_path):
        # A missing changed path produces one HIGH implementation finding.
        result = trigger_gap_run(
            repository_root=tmp_path,
            trigger_type=TriggerType.FILE_APPLIED,
            changed_paths=["missing.py"],
        )
        assert result["status"] == "success"
        trigger = result["result"]
        assert trigger["triggered"] is True
        assert trigger["finding_count"] == 1

        record = get_gap_record(tmp_path, trigger["gap_run_id"])
        assert record["status"] == "success"
        # finding_count parity: persisted record keeps the live findings.
        assert len(record["result"]["findings"]) == trigger["finding_count"]
        assert record["result"]["final_result"] == "completed"

    def test_trigger_duplicate_digest_replays(self, tmp_path):
        (tmp_path / "module.py").write_text("def hello(): pass")
        first = trigger_gap_run(
            repository_root=tmp_path,
            trigger_type=TriggerType.FILE_APPLIED,
            changed_paths=["module.py"],
        )
        assert first["result"]["triggered"] is True

        second = trigger_gap_run(
            repository_root=tmp_path,
            trigger_type=TriggerType.FILE_APPLIED,
            changed_paths=["module.py"],
        )
        assert second["result"]["triggered"] is False
        assert second["result"]["reason"] == "duplicate_trigger"
        assert second["result"]["existing_gap_run_id"] == first["result"]["gap_run_id"]

    def test_trigger_skips_non_apply_events(self, tmp_path):
        result = trigger_gap_run(
            repository_root=tmp_path,
            trigger_type=TriggerType.EXECUTION_FAILURE,
        )
        assert result["status"] == "success"
        assert result["result"]["triggered"] is False
        assert result["result"]["reason"] == "auto_disabled_or_not_applicable"


class TestCompletionAnalysis:
    """analyze_completion produces persisted evidence, never completion authority."""

    def test_analyze_completion_persists_evidence_incomplete(self, tmp_path):
        result = analyze_completion(
            repository_root=tmp_path,
            task_id="task-1",
            success_definition="all tests pass",
        )
        assert result["status"] == "success"
        payload = result["result"]
        assert payload["persisted"] is True
        assert payload["analysis_status"] == EVIDENCE_INCOMPLETE
        assert payload["no_material_gap"] is False

        record = get_gap_record(tmp_path, payload["gap_run_id"])
        assert record["status"] == "success"
        assert record["result"]["final_result"] == EVIDENCE_INCOMPLETE
        assert record["result"]["trigger_type"] == "implementation_complete"
