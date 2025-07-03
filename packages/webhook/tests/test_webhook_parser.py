"""Tests for webhook parsing functionality."""

import json
import pytest
from devs_webhook.github.parser import WebhookParser
from devs_webhook.github.models import IssueEvent, CommentEvent


class TestWebhookParser:
    """Test webhook parsing functionality."""
    
    def test_parse_issue_event(self):
        """Test parsing issue webhook events."""
        # Mock issue event payload
        payload = {
            "action": "opened",
            "issue": {
                "id": 1,
                "number": 123,
                "title": "Test issue",
                "body": "Please @testuser take a look at this bug",
                "state": "open",
                "user": {
                    "login": "reporter",
                    "id": 456,
                    "avatar_url": "https://github.com/avatar.jpg",
                    "html_url": "https://github.com/reporter"
                },
                "html_url": "https://github.com/test/repo/issues/123",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z"
            },
            "repository": {
                "id": 789,
                "name": "repo",
                "full_name": "test/repo",
                "owner": {
                    "login": "test",
                    "id": 111,
                    "avatar_url": "https://github.com/avatar.jpg",
                    "html_url": "https://github.com/test"
                },
                "html_url": "https://github.com/test/repo",
                "clone_url": "https://github.com/test/repo.git",
                "ssh_url": "git@github.com:test/repo.git",
                "default_branch": "main"
            },
            "sender": {
                "login": "reporter",
                "id": 456,
                "avatar_url": "https://github.com/avatar.jpg",
                "html_url": "https://github.com/reporter"
            }
        }
        
        headers = {"x-github-event": "issues"}
        payload_bytes = json.dumps(payload).encode()
        
        event = WebhookParser.parse_webhook(headers, payload_bytes)
        
        assert isinstance(event, IssueEvent)
        assert event.action == "opened"
        assert event.issue.number == 123
        assert event.issue.title == "Test issue"
        assert event.repository.full_name == "test/repo"
    
    def test_should_process_event_with_mention(self):
        """Test that events with mentions are processed."""
        # Create a mock issue event
        payload = {
            "action": "opened",
            "issue": {
                "id": 1,
                "number": 123,
                "title": "Test issue",
                "body": "Hey @testuser can you help with this?",
                "state": "open",
                "user": {
                    "login": "reporter",
                    "id": 456,
                    "avatar_url": "https://github.com/avatar.jpg",
                    "html_url": "https://github.com/reporter"
                },
                "html_url": "https://github.com/test/repo/issues/123",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z"
            },
            "repository": {
                "id": 789,
                "name": "repo",
                "full_name": "test/repo",
                "owner": {
                    "login": "test",
                    "id": 111,
                    "avatar_url": "https://github.com/avatar.jpg",
                    "html_url": "https://github.com/test"
                },
                "html_url": "https://github.com/test/repo",
                "clone_url": "https://github.com/test/repo.git",
                "ssh_url": "git@github.com:test/repo.git",
                "default_branch": "main"
            },
            "sender": {
                "login": "reporter",
                "id": 456,
                "avatar_url": "https://github.com/avatar.jpg",
                "html_url": "https://github.com/reporter"
            }
        }
        
        headers = {"x-github-event": "issues"}
        payload_bytes = json.dumps(payload).encode()
        
        event = WebhookParser.parse_webhook(headers, payload_bytes)
        should_process = WebhookParser.should_process_event(event, "testuser")
        
        assert should_process is True
    
    def test_should_not_process_event_without_mention(self):
        """Test that events without mentions are not processed."""
        payload = {
            "action": "opened",
            "issue": {
                "id": 1,
                "number": 123,
                "title": "Test issue",
                "body": "This is a regular issue without mentions",
                "state": "open",
                "user": {
                    "login": "reporter",
                    "id": 456,
                    "avatar_url": "https://github.com/avatar.jpg",
                    "html_url": "https://github.com/reporter"
                },
                "html_url": "https://github.com/test/repo/issues/123",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z"
            },
            "repository": {
                "id": 789,
                "name": "repo",
                "full_name": "test/repo",
                "owner": {
                    "login": "test",
                    "id": 111,
                    "avatar_url": "https://github.com/avatar.jpg",
                    "html_url": "https://github.com/test"
                },
                "html_url": "https://github.com/test/repo",
                "clone_url": "https://github.com/test/repo.git",
                "ssh_url": "git@github.com:test/repo.git",
                "default_branch": "main"
            },
            "sender": {
                "login": "reporter",
                "id": 456,
                "avatar_url": "https://github.com/avatar.jpg",
                "html_url": "https://github.com/reporter"
            }
        }
        
        headers = {"x-github-event": "issues"}
        payload_bytes = json.dumps(payload).encode()
        
        event = WebhookParser.parse_webhook(headers, payload_bytes)
        should_process = WebhookParser.should_process_event(event, "testuser")
        
        assert should_process is False
    
    def test_unsupported_event_type(self):
        """Test that unsupported event types return None."""
        payload = {"action": "test"}
        headers = {"x-github-event": "unsupported"}
        payload_bytes = json.dumps(payload).encode()
        
        event = WebhookParser.parse_webhook(headers, payload_bytes)
        assert event is None
    
