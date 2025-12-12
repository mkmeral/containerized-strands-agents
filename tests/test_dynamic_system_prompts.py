"""Tests for dynamic system prompt list feature."""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestDynamicSystemPrompts:
    """Tests for dynamic system prompt list functionality."""

    @pytest.fixture
    def temp_prompts(self, tmp_path):
        """Create temporary system prompt files for testing."""
        # File with # comment for display name
        code_reviewer = tmp_path / "code_reviewer.txt"
        code_reviewer.write_text("# Advanced Code Review Assistant\nYou are a code reviewer.")
        
        # File with # comment for display name
        data_analyst = tmp_path / "data_analyst.txt"
        data_analyst.write_text("# Data Analysis Specialist\nYou are a data analyst.")
        
        # File without # comment (should use filename)
        simple_helper = tmp_path / "simple_helper.txt"
        simple_helper.write_text("You are a helpful assistant.")
        
        return {
            'code_reviewer': str(code_reviewer),
            'data_analyst': str(data_analyst),
            'simple_helper': str(simple_helper)
        }

    def test_parse_system_prompts_env_empty(self):
        """Test parsing when environment variable is not set."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        with patch.dict(os.environ, {}, clear=True):
            result = _parse_system_prompts_env()
            assert result == []

    def test_parse_system_prompts_env_valid_files(self, temp_prompts):
        """Test parsing with valid system prompt files."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        env_value = f"{temp_prompts['code_reviewer']},{temp_prompts['data_analyst']},{temp_prompts['simple_helper']}"
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
            result = _parse_system_prompts_env()
            
            assert len(result) == 3
            
            # Check names extracted from # comments
            names = [p['name'] for p in result]
            assert "Advanced Code Review Assistant" in names
            assert "Data Analysis Specialist" in names
            assert "simple_helper" in names  # No # comment, uses filename
            
            # Check paths
            paths = [p['path'] for p in result]
            assert temp_prompts['code_reviewer'] in paths
            assert temp_prompts['data_analyst'] in paths
            assert temp_prompts['simple_helper'] in paths

    def test_parse_system_prompts_env_with_nonexistent_files(self, temp_prompts):
        """Test parsing with mix of existing and nonexistent files."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        env_value = f"{temp_prompts['code_reviewer']},/nonexistent/file.txt,{temp_prompts['data_analyst']}"
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
            result = _parse_system_prompts_env()
            
            # Should only include existing files
            assert len(result) == 2
            names = [p['name'] for p in result]
            assert "Advanced Code Review Assistant" in names
            assert "Data Analysis Specialist" in names

    def test_parse_system_prompts_env_with_directories(self, tmp_path):
        """Test that directories are skipped."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        # Create a directory
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        
        # Create a valid file
        valid_file = tmp_path / "valid.txt"
        valid_file.write_text("# Valid File\nContent")
        
        env_value = f"{str(test_dir)},{str(valid_file)}"
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
            result = _parse_system_prompts_env()
            
            # Should only include the file, not the directory
            assert len(result) == 1
            assert result[0]['name'] == "Valid File"

    def test_parse_system_prompts_env_with_whitespace(self, temp_prompts):
        """Test parsing with whitespace in environment variable."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        # Add extra whitespace and empty entries
        env_value = f" {temp_prompts['code_reviewer']} , , {temp_prompts['data_analyst']} , "
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
            result = _parse_system_prompts_env()
            
            assert len(result) == 2
            names = [p['name'] for p in result]
            assert "Advanced Code Review Assistant" in names
            assert "Data Analysis Specialist" in names

    def test_parse_system_prompts_env_with_tilde_expansion(self, tmp_path):
        """Test that tilde expansion works."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        # Create a test file in tmp_path
        test_file = tmp_path / "test.txt"
        test_file.write_text("# Tilde Test\nContent")
        
        # Mock expanduser to return our test file
        with patch('pathlib.Path.expanduser') as mock_expand:
            mock_expand.return_value = test_file
            
            env_value = "~/test.txt"
            with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
                result = _parse_system_prompts_env()
                
                assert len(result) == 1
                assert result[0]['name'] == "Tilde Test"
                mock_expand.assert_called_once()

    def test_build_send_message_docstring_without_prompts(self):
        """Test docstring generation when no prompts are available."""
        from containerized_strands_agents.server import _build_send_message_docstring
        
        with patch.dict(os.environ, {}, clear=True):
            docstring = _build_send_message_docstring()
            
            # Should contain base docstring but no prompts section
            assert "Send a message to an agent" in docstring
            assert "system_prompt_file" in docstring
            assert "Available system prompts:" not in docstring

    def test_build_send_message_docstring_with_prompts(self, temp_prompts):
        """Test docstring generation when prompts are available."""
        from containerized_strands_agents.server import _build_send_message_docstring
        
        env_value = f"{temp_prompts['code_reviewer']},{temp_prompts['data_analyst']}"
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
            docstring = _build_send_message_docstring()
            
            # Should contain base docstring and prompts section
            assert "Send a message to an agent" in docstring
            assert "system_prompt_file" in docstring
            assert "Available system prompts:" in docstring
            assert "Advanced Code Review Assistant" in docstring
            assert "Data Analysis Specialist" in docstring
            assert temp_prompts['code_reviewer'] in docstring
            assert temp_prompts['data_analyst'] in docstring

    def test_parse_system_prompts_file_read_error(self, tmp_path):
        """Test handling of file read errors."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("# Test File\nContent")
        
        # Mock open to raise PermissionError
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            env_value = str(test_file)
            
            with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
                result = _parse_system_prompts_env()
                
                # Should still include the file but use filename as fallback
                assert len(result) == 1
                assert result[0]['name'] == "test"  # filename without extension

    def test_parse_system_prompts_multiline_comment(self, tmp_path):
        """Test extracting display name from multiline comment."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        # Create file with multiline content where first line is # comment
        test_file = tmp_path / "multiline.txt"
        test_file.write_text("# Multi Line Assistant\nSecond line\nThird line\n# Another comment")
        
        env_value = str(test_file)
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
            result = _parse_system_prompts_env()
            
            assert len(result) == 1
            assert result[0]['name'] == "Multi Line Assistant"  # Only first line used

    def test_parse_system_prompts_no_comment_uses_filename(self, tmp_path):
        """Test that filename is used when no # comment exists."""
        from containerized_strands_agents.server import _parse_system_prompts_env
        
        # Create file without # comment
        test_file = tmp_path / "my_special_assistant.txt"
        test_file.write_text("You are a helpful assistant without a comment.")
        
        env_value = str(test_file)
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": env_value}):
            result = _parse_system_prompts_env()
            
            assert len(result) == 1
            assert result[0]['name'] == "my_special_assistant"  # filename without extension
