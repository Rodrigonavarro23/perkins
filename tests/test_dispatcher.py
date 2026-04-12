"""
Unit tests for FlowDispatcher and DispatchQueue — covers:
  - Scenario: Watcher detects a new GitHub issue and dispatches it to the Master
  - Scenario: Master queues a dispatched issue when the concurrency limit is reached
"""
from pathlib import Path

from perkins.dispatcher import DispatchQueue, FlowDispatcher
from perkins.models import FlowState, FlowStatus
from perkins.watcher import IssueRegistry


# ── DispatchQueue ───────────────────────────────────────────────────────────

def test_dispatch_queue_enqueue_then_dequeue():
    q = DispatchQueue()
    q.enqueue("42")
    assert q.dequeue() == "42"


def test_dispatch_queue_dequeue_empty_returns_none():
    q = DispatchQueue()
    assert q.dequeue() is None


def test_dispatch_queue_is_queued_true_after_enqueue():
    q = DispatchQueue()
    q.enqueue("42")
    assert q.is_queued("42") is True


def test_dispatch_queue_is_queued_false_before_enqueue():
    q = DispatchQueue()
    assert q.is_queued("42") is False


def test_dispatch_queue_fifo_ordering():
    q = DispatchQueue()
    q.enqueue("1")
    q.enqueue("2")
    q.enqueue("3")
    assert q.dequeue() == "1"
    assert q.dequeue() == "2"
    assert q.dequeue() == "3"


def test_dispatch_queue_size():
    q = DispatchQueue()
    q.enqueue("1")
    q.enqueue("2")
    assert q.size() == 2


def test_dispatch_queue_size_zero_when_empty():
    q = DispatchQueue()
    assert q.size() == 0


# ── FlowDispatcher — below concurrency limit ────────────────────────────────

def test_flow_dispatcher_creates_dispatched_flow_when_below_limit(tmp_path):
    (tmp_path / "flows").mkdir()
    dispatcher = FlowDispatcher(IssueRegistry(), DispatchQueue(), max_concurrent=3)
    flow = dispatcher.dispatch("42", tmp_path, active_flows_count=0)
    assert flow.status == FlowStatus.dispatched


def test_flow_dispatcher_writes_flow_file_when_below_limit(tmp_path):
    (tmp_path / "flows").mkdir()
    dispatcher = FlowDispatcher(IssueRegistry(), DispatchQueue(), max_concurrent=3)
    dispatcher.dispatch("42", tmp_path, active_flows_count=0)
    flow_file = tmp_path / "flows" / "42.json"
    assert flow_file.exists()
    state = FlowState.model_validate_json(flow_file.read_text())
    assert state.issue_id == "42"
    assert state.status == FlowStatus.dispatched


def test_flow_dispatcher_does_not_enqueue_when_below_limit(tmp_path):
    (tmp_path / "flows").mkdir()
    queue = DispatchQueue()
    dispatcher = FlowDispatcher(IssueRegistry(), queue, max_concurrent=3)
    dispatcher.dispatch("42", tmp_path, active_flows_count=2)
    assert queue.is_queued("42") is False


def test_flow_dispatcher_tracks_issue_in_registry_when_below_limit(tmp_path):
    (tmp_path / "flows").mkdir()
    registry = IssueRegistry()
    dispatcher = FlowDispatcher(registry, DispatchQueue(), max_concurrent=3)
    dispatcher.dispatch("42", tmp_path, active_flows_count=0)
    assert registry.is_tracked("42") is True


# ── FlowDispatcher — at concurrency limit ───────────────────────────────────

def test_flow_dispatcher_creates_queued_flow_when_at_limit(tmp_path):
    (tmp_path / "flows").mkdir()
    dispatcher = FlowDispatcher(IssueRegistry(), DispatchQueue(), max_concurrent=3)
    flow = dispatcher.dispatch("55", tmp_path, active_flows_count=3)
    assert flow.status == FlowStatus.queued


def test_flow_dispatcher_writes_queued_flow_file_when_at_limit(tmp_path):
    (tmp_path / "flows").mkdir()
    dispatcher = FlowDispatcher(IssueRegistry(), DispatchQueue(), max_concurrent=3)
    dispatcher.dispatch("55", tmp_path, active_flows_count=3)
    flow_file = tmp_path / "flows" / "55.json"
    assert flow_file.exists()
    state = FlowState.model_validate_json(flow_file.read_text())
    assert state.issue_id == "55"
    assert state.status == FlowStatus.queued


def test_flow_dispatcher_enqueues_issue_when_at_limit(tmp_path):
    (tmp_path / "flows").mkdir()
    queue = DispatchQueue()
    dispatcher = FlowDispatcher(IssueRegistry(), queue, max_concurrent=3)
    dispatcher.dispatch("55", tmp_path, active_flows_count=3)
    assert queue.is_queued("55") is True


def test_flow_dispatcher_also_tracks_queued_issue_in_registry(tmp_path):
    (tmp_path / "flows").mkdir()
    registry = IssueRegistry()
    dispatcher = FlowDispatcher(registry, DispatchQueue(), max_concurrent=3)
    dispatcher.dispatch("55", tmp_path, active_flows_count=3)
    assert registry.is_tracked("55") is True


def test_flow_dispatcher_flow_file_has_no_tmp_artifacts(tmp_path):
    (tmp_path / "flows").mkdir()
    dispatcher = FlowDispatcher(IssueRegistry(), DispatchQueue(), max_concurrent=3)
    dispatcher.dispatch("42", tmp_path, active_flows_count=0)
    assert list((tmp_path / "flows").glob("*.tmp")) == []


# ── FlowDispatcher — exact limit boundary ───────────────────────────────────

def test_flow_dispatcher_dispatches_when_one_below_limit(tmp_path):
    (tmp_path / "flows").mkdir()
    dispatcher = FlowDispatcher(IssueRegistry(), DispatchQueue(), max_concurrent=5)
    flow = dispatcher.dispatch("42", tmp_path, active_flows_count=4)
    assert flow.status == FlowStatus.dispatched


def test_flow_dispatcher_queues_when_at_limit_of_one(tmp_path):
    (tmp_path / "flows").mkdir()
    dispatcher = FlowDispatcher(IssueRegistry(), DispatchQueue(), max_concurrent=1)
    flow = dispatcher.dispatch("42", tmp_path, active_flows_count=1)
    assert flow.status == FlowStatus.queued
