import create_service_account
import unittest
import sys
import os
import argparse
import asyncio
import re
from unittest.mock import patch, MagicMock, AsyncMock

# Add parent directory to sys.path to import create_service_account
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCreateServiceAccount(unittest.TestCase):

  def setUp(self):
    # Reset global variables before each test
    create_service_account.TOOL_NAME = ""
    create_service_account.TOOL_NAME_FRIENDLY = ""
    create_service_account.TOOL_HELP_CENTER_URL = ""
    create_service_account.APIS = []
    create_service_account.SCOPES = []

  def test_gwmme_config(self):
    args = argparse.Namespace(tool="gwmme",
                              tool_name=None,
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None,
                              no_key=False)
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME, "GWMME")
    self.assertEqual(create_service_account.TOOL_NAME_FRIENDLY,
                     "Google Workspace Migration for Microsoft Exchange")
    self.assertIn("admin.googleapis.com", create_service_account.APIS)
    self.assertIn("orgpolicy.googleapis.com", create_service_account.APIS)
    self.assertIn("https://www.googleapis.com/auth/contacts",
                  create_service_account.SCOPES)

  def test_gwmme_config_no_key(self):
    # orgpolicy should NOT be removed even if no_key is True
    args = argparse.Namespace(tool="gwmme",
                              tool_name=None,
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None,
                              no_key=True)
    create_service_account.setup_config(args)
    self.assertIn("admin.googleapis.com", create_service_account.APIS)
    self.assertIn("orgpolicy.googleapis.com", create_service_account.APIS)

  def test_admin_api_ordering(self):
    # admin.googleapis.com should be first
    args = argparse.Namespace(tool="gwmme",
                              tool_name=None,
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None,
                              no_key=False)
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.APIS[0], "admin.googleapis.com")

  def test_case_insensitive_tool(self):
    args = argparse.Namespace(tool="GwMmE",
                              tool_name=None,
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None,
                              no_key=False)
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME, "GWMME")

  @patch('builtins.input', side_effect=['1'])
  def test_invalid_tool_fallback(self, mock_input):
    # Invalid tool should trigger interactive selection
    args = argparse.Namespace(tool="invalid_tool",
                              tool_name=None,
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None,
                              no_key=False)
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME, "GWMME")

  def test_defaults(self):
    args = argparse.Namespace(tool=None,
                              tool_name="MyTool",
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis="admin",
                              scopes="scope1",
                              no_key=False)
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME_FRIENDLY, "MyTool")
    self.assertEqual(create_service_account.TOOL_HELP_CENTER_URL,
                     "the documentation for MyTool")

  def test_invalid_tool_name_validation(self):
    args = argparse.Namespace(tool=None,
                              tool_name="Bad@Name",
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None,
                              no_key=False)
    with self.assertRaises(SystemExit):
      create_service_account.setup_config(args)

  def test_valid_tool_name_validation(self):
    args = argparse.Namespace(tool=None,
                              tool_name="Good-Name' 123!",
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis="admin",
                              scopes="scope1",
                              no_key=False)
    # Should not raise
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME, "Good-Name' 123!")

  @patch('create_service_account.retryable_command', new_callable=AsyncMock)
  def test_project_name_truncation(self, mock_retryable):
    create_service_account.TOOL_NAME = "ThisIsAVeryLongToolNameThatExceedsLimit"
    asyncio.run(create_service_account.create_project())

    # Check the command passed to retryable_command
    call_args = mock_retryable.call_args[0][0]
    match = re.search(r"--name '([^']+)'", call_args)
    self.assertTrue(match, "Could not find --name argument in command")
    project_name = match.group(1)

    # Max length is 30
    self.assertLessEqual(len(project_name), 30)
    # Suffix is 16 chars (-YYYYMMDD-HHMMSS), so prefix should be 14
    self.assertTrue(project_name.startswith("ThisIsAVeryLon-"))

  @patch('create_service_account.get_service_account_email',
         new_callable=AsyncMock)
  @patch('create_service_account.retryable_command',
         new_callable=AsyncMock)
  @patch('create_service_account.Http.request')
  @patch('create_service_account.os.path.exists')
  def test_get_access_token_no_key(self, mock_exists, mock_request,
                                   mock_retryable, mock_get_email):
    # Setup mocks
    mock_exists.return_value = False  # KEY_FILE does not exist
    create_service_account.KEY_FILE = "dummy_key.json"
    create_service_account.TOOL_NAME = "TestTool"
    # Mock get_service_account_email (async)
    mock_get_email.return_value = "tool-service-account@test-project.iam.gserviceaccount.com"
    # Mock retryable_command (async)
    mock_retryable.return_value = (b"signed_jwt_content", b"", 0)
    # Mock Http request for token exchange
    mock_request.return_value = (unittest.mock.Mock(status=200),
                                 b'{"access_token": "mock_access_token"}')
    token = asyncio.run(
        create_service_account.get_access_token_for_scopes(
            "user@example.com", ["scope1"]))
    self.assertEqual(token, "mock_access_token")

if __name__ == '__main__':
  unittest.main()
