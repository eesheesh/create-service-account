import create_service_account
import unittest
import sys
import os
import argparse
import asyncio
from unittest.mock import patch
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
                              scopes=None)
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME, "GWMME")
    self.assertEqual(create_service_account.TOOL_NAME_FRIENDLY,
                     "Google Workspace Migration for Microsoft Exchange")
    self.assertIn("admin.googleapis.com", create_service_account.APIS)
    self.assertIn("https://www.googleapis.com/auth/contacts",
                  create_service_account.SCOPES)

  def test_gwm_config(self):
    args = argparse.Namespace(tool="gwm",
                              tool_name=None,
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None)
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME, "GWM")
    self.assertEqual(create_service_account.TOOL_NAME_FRIENDLY,
                     "Google Workspace Migrate")
    self.assertIn("migrate.googleapis.com", create_service_account.APIS)

  def test_password_sync_config(self):
    args = argparse.Namespace(tool="password_sync",
                              tool_name=None,
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None)
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME, "PasswordSync")
    self.assertEqual(create_service_account.TOOL_NAME_FRIENDLY, "Password Sync")

  def test_custom_arguments_override(self):
    args = argparse.Namespace(tool="gwmme",
                              tool_name="CustomTool",
                              tool_friendly_name="My Custom Tool",
                              help_center_url="https://custom.url",
                              apis="api1,api2.com",
                              scopes="scope1,https://scope2")
    create_service_account.setup_config(args)
    self.assertEqual(create_service_account.TOOL_NAME, "CustomTool")
    self.assertEqual(create_service_account.TOOL_NAME_FRIENDLY,
                     "My Custom Tool")
    self.assertEqual(create_service_account.TOOL_HELP_CENTER_URL,
                     "https://custom.url")
    self.assertEqual(create_service_account.APIS,
                     ["api1.googleapis.com", "api2.com"])
    self.assertEqual(
        create_service_account.SCOPES,
        ["https://www.googleapis.com/auth/scope1", "https://scope2"])

  def test_missing_tool_name_exits(self):
    args = argparse.Namespace(tool=None,
                              tool_name=None,
                              tool_friendly_name=None,
                              help_center_url=None,
                              apis=None,
                              scopes=None)
    with self.assertRaises(SystemExit):
      create_service_account.setup_config(args)

  def test_api_suffix_logic(self):
    args = argparse.Namespace(tool="gwmme",
                              tool_name="TestTool",
                              tool_friendly_name="Test Tool",
                              help_center_url="https://example.com",
                              apis="admin,calendar-json,custom.api.com",
                              scopes=None)
    create_service_account.setup_config(args)
    expected_apis = [
        "admin.googleapis.com", "calendar-json.googleapis.com", "custom.api.com"
    ]
    self.assertEqual(create_service_account.APIS, expected_apis)

  def test_scope_prefix_logic(self):
    args = argparse.Namespace(
        tool="gwmme",
        tool_name="TestTool",
        tool_friendly_name="Test Tool",
        help_center_url="https://example.com",
        apis=None,
        scopes="admin.directory.user,https://www.googleapis.com/auth/calendar")
    create_service_account.setup_config(args)
    expected_scopes = [
        "https://www.googleapis.com/auth/admin.directory.user",
        "https://www.googleapis.com/auth/calendar"
    ]
    self.assertEqual(create_service_account.SCOPES, expected_scopes)

  @patch('create_service_account.get_service_account_email',
         new_callable=unittest.mock.AsyncMock)
  @patch('create_service_account.retryable_command',
         new_callable=unittest.mock.AsyncMock)
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
    # Verify gcloud command was called via retryable_command
    # Expected command substring
    mock_retryable.assert_called()
    # Check if sign-jwt was called
    found_sign_jwt = False
    for call_args in mock_retryable.call_args_list:
      command = call_args[0][0]
      if "sign-jwt" in command:
        found_sign_jwt = True
        break
    self.assertTrue(found_sign_jwt,
                    "gcloud iam service-accounts sign-jwt was not called")
    # Verify token exchange request
    mock_request.assert_called()
    call_args = mock_request.call_args
    self.assertEqual(call_args[0][0], "https://oauth2.googleapis.com/token")
    self.assertEqual(call_args[0][1], "POST")
    self.assertIn(
        "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer",
        call_args[1]['body'])
    self.assertIn("assertion=signed_jwt_content", call_args[1]['body'])

  def test_is_service_disabled(self):
    # Test disabled scenarios
    self.assertTrue(
        create_service_account.is_service_disabled(
            '{"error": {"errors": [{"reason": "notACalendarUser"}]}}'))
    self.assertTrue(
        create_service_account.is_service_disabled(
            '{"error": {"errors": [{"reason": "notFound"}]}}'))
    self.assertTrue(
        create_service_account.is_service_disabled(
            '{"error": {"errors": [{"reason": "authError"}]}}'))
    self.assertTrue(
        create_service_account.is_service_disabled(
            '{"error": {"message": "service not enabled"}}'))
    # Test enabled scenarios
    self.assertFalse(
        create_service_account.is_service_disabled(
            '{"error": {"errors": [{"reason": "otherError"}]}}'))
    self.assertFalse(create_service_account.is_service_disabled('{}'))
    self.assertTrue(create_service_account.is_service_disabled(None))


if __name__ == '__main__':
  unittest.main()
