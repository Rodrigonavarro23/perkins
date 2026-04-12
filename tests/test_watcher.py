"""
Unit tests for the Watcher IssueRegistry — covers:
  - Scenario: Watcher skips an issue already in the active flow registry
"""
from perkins.watcher import IssueRegistry


def test_new_registry_can_dispatch_any_issue():
    registry = IssueRegistry()
    assert registry.can_dispatch("42") is True


def test_tracked_issue_cannot_be_dispatched():
    registry = IssueRegistry()
    registry.track("42")
    assert registry.can_dispatch("42") is False


def test_untracked_issue_is_still_dispatchable_after_another_is_tracked():
    registry = IssueRegistry()
    registry.track("42")
    assert registry.can_dispatch("55") is True


def test_is_tracked_false_for_new_issue():
    registry = IssueRegistry()
    assert registry.is_tracked("42") is False


def test_is_tracked_true_after_tracking():
    registry = IssueRegistry()
    registry.track("42")
    assert registry.is_tracked("42") is True


def test_track_is_idempotent():
    registry = IssueRegistry()
    registry.track("42")
    registry.track("42")
    assert registry.is_tracked("42") is True
    assert registry.can_dispatch("42") is False


def test_multiple_issues_tracked_independently():
    registry = IssueRegistry()
    registry.track("1")
    registry.track("2")
    registry.track("3")
    assert registry.is_tracked("1")
    assert registry.is_tracked("2")
    assert registry.is_tracked("3")
    assert not registry.is_tracked("4")
    assert registry.can_dispatch("4") is True
