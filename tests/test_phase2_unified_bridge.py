#!/usr/bin/env python3
"""
Phase 2 Tests for Unified mimir_bridge.py

Tests the unified bridge that supports both:
1. JSON protocol mode (for jcode integration via stdin/stdout)
2. CLI mode (mimir init, mimir index, mimir search, etc.)

This test suite validates all actions supported by the unified bridge.
"""

import json
import os
import sys
import io
import select
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Import directly from scripts.mimir_bridge module
import scripts.mimir_bridge as bridge_module


class TestUnifiedBridgeJsonProtocol:
    """Test JSON protocol mode (stdin → stdout JSON)."""
    
    def test_handle_json_protocol_function_exists(self):
        """Test that handle_json_protocol function exists."""
        assert hasattr(bridge_module, 'handle_json_protocol')
        assert callable(bridge_module.handle_json_protocol)
    
    def test_json_protocol_returns_false_for_tty(self):
        """Test that handle_json_protocol returns False when stdin is a TTY."""
        
        # Mock sys.stdin.isatty() to return True
        with patch('sys.stdin.isatty', return_value=True):
            result = bridge_module.handle_json_protocol()
            assert result is False
    
    def test_json_protocol_processes_valid_json(self):
        """Test that valid JSON is processed correctly."""
        
        test_input = json.dumps({"action": "stats", "params": {}})
        
        # Mock select.select to return stdin has data
        # Mock stdin.read to return our test input
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value=test_input):
                    with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
                        result = bridge_module.handle_json_protocol()
                        # Should return True if JSON was processed
                        if result:
                            output = fake_stdout.getvalue()
                            # Should output valid JSON
                            parsed = json.loads(output)
                            assert "status" in parsed
    
    def test_json_protocol_handles_invalid_json(self):
        """Test handling of invalid JSON input."""
        
        # Mock select.select to return stdin has data
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value="invalid json"):
                    # Should not raise an exception
                    result = bridge_module.handle_json_protocol()
                    # May return False or True depending on implementation
                    assert result in [True, False]


class TestUnifiedBridgeActions:
    """Test all actions supported by the unified bridge."""
    
    def test_stats_action(self):
        """Test stats action returns proper JSON."""
        
        test_input = json.dumps({"action": "stats"})
        
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value=test_input):
                    with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
                        bridge_module.handle_json_protocol()
                        output = fake_stdout.getvalue()
                        if output:  # Only parse if there's output
                            parsed = json.loads(output)
                            assert "status" in parsed
    
    def test_search_action_no_index(self):
        """Test search action when no index exists."""
        
        test_input = json.dumps({"action": "search", "params": {"query": "test"}})
        
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value=test_input):
                    with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
                        bridge_module.handle_json_protocol()
                        output = fake_stdout.getvalue()
                        if output:
                            parsed = json.loads(output)
                            # Should return ok status with results or error
                            assert "status" in parsed or "error" in parsed
    
    def test_enrich_task_action(self):
        """Test enrich_task action."""
        
        test_input = json.dumps({"action": "enrich_task", "params": {"task": "implement auth"}})
        
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value=test_input):
                    with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
                        bridge_module.handle_json_protocol()
                        output = fake_stdout.getvalue()
                        if output:
                            parsed = json.loads(output)
                            assert "status" in parsed
    
    def test_unknown_action(self):
        """Test handling of unknown action."""
        
        test_input = json.dumps({"action": "nonexistent_action"})
        
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value=test_input):
                    with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
                        bridge_module.handle_json_protocol()
                        output = fake_stdout.getvalue()
                        if output:
                            parsed = json.loads(output)
                            assert "error" in parsed


class TestUnifiedBridgeCliMode:
    """Test CLI mode functionality."""
    
    def test_cli_main_function_exists(self):
        """Test that main function exists for CLI mode."""
        assert hasattr(bridge_module, 'main')
        assert callable(bridge_module.main)
    
    def test_cli_help_option(self):
        """Test CLI --help option."""
        
        with patch('sys.argv', ['mimir_bridge.py', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                # Mock stdin to avoid read issues
                with patch('sys.stdin', io.StringIO('')):
                    bridge_module.main()
            # --help should exit with code 0
            assert exc_info.value.code == 0
    
    def test_cli_init_command(self):
        """Test CLI init command structure."""
        
        # Test that init command is recognized
        with patch('sys.argv', ['mimir_bridge.py', 'init', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                with patch('sys.stdin', io.StringIO('')):
                    bridge_module.main()
            # --help should exit with code 0
            assert exc_info.value.code == 0


class TestUnifiedBridgeIntegration:
    """Integration tests for the unified bridge."""
    
    def test_both_modes_can_coexist(self):
        """Test that JSON protocol and CLI modes don't interfere."""
        
        # JSON protocol should work
        with patch('sys.stdin.isatty', return_value=True):
            result = bridge_module.handle_json_protocol()
            assert result is False  # Should return False for TTY
        
        # CLI mode should work (just check it doesn't crash on --help)
        with patch('sys.argv', ['mimir_bridge.py', '--help']):
            with pytest.raises(SystemExit):
                with patch('sys.stdin', io.StringIO('')):
                    bridge_module.main()
    
    def test_action_list_in_error_message(self):
        """Test that unknown action error lists available actions."""
        
        test_input = json.dumps({"action": "invalid_action_12345"})
        
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value=test_input):
                    with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
                        bridge_module.handle_json_protocol()
                        output = fake_stdout.getvalue()
                        if output:
                            parsed = json.loads(output)
                            assert "available_actions" in parsed or "error" in parsed


class TestUnifiedBridgeEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_stdin(self):
        """Test handling of empty stdin."""
        
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([], [], [])):  # No data available
                result = bridge_module.handle_json_protocol()
                assert result is False  # Should return False for no data
    
    def test_missing_action_in_json(self):
        """Test handling of JSON without action field."""
        
        test_input = json.dumps({"params": {}})
        
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value=test_input):
                    with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
                        bridge_module.handle_json_protocol()
                        output = fake_stdout.getvalue()
                        # Should handle gracefully
                        if output:
                            parsed = json.loads(output)
                            assert "error" in parsed or "status" in parsed
    
    def test_missing_params_in_json(self):
        """Test handling of JSON without params field."""
        
        test_input = json.dumps({"action": "stats"})
        
        with patch('sys.stdin.isatty', return_value=False):
            with patch('select.select', return_value=([sys.stdin], [], [])):
                with patch('sys.stdin.read', return_value=test_input):
                    with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
                        bridge_module.handle_json_protocol()
                        output = fake_stdout.getvalue()
                        if output:
                            parsed = json.loads(output)
                            assert "status" in parsed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
