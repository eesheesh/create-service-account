import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
import json
import datetime
import itertools
import create_service_account

# Add parent directory to sys.path to import create_service_account
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestCreateServiceAccountIntegration(unittest.TestCase):

    def setUp(self):
        # Reset global variables
        create_service_account.TOOL_NAME = ""
        create_service_account.TOOL_NAME_FRIENDLY = ""
        create_service_account.TOOL_HELP_CENTER_URL = ""
        create_service_account.APIS = []
        create_service_account.SCOPES = []

        # Patch input to always return empty string (Enter) or '1'
        self.patcher_input = patch('builtins.input', side_effect=itertools.cycle(['']))
        self.mock_input = self.patcher_input.start()

        # Patch print/stdout to capture output
        # self.patcher_stdout = patch('sys.stdout', new_callable=MagicMock)
        # self.mock_stdout = self.patcher_stdout.start()

        # Patch logging to suppress output during tests but allow capture if needed
        self.patcher_logging = patch('create_service_account.logging')
        self.mock_logging = self.patcher_logging.start()

        # Patch os.system (for clear)
        self.patcher_os_system = patch('os.system')
        self.mock_os_system = self.patcher_os_system.start()

        # Patch subprocess.Popen (synchronous)
        self.patcher_subprocess = patch('subprocess.Popen', new_callable=MagicMock)
        self.mock_subprocess_popen = self.patcher_subprocess.start()

        # Patch httplib2.Http
        self.patcher_http = patch('create_service_account.Http')
        self.mock_http_class = self.patcher_http.start()
        self.mock_http_instance = self.mock_http_class.return_value
        self.mock_http_instance.request = MagicMock(return_value=(MagicMock(status=200), b'{}'))

        # Patch Request
        self.patcher_request = patch('create_service_account.Request')
        self.mock_request_class = self.patcher_request.start()

        # Patch service_account.Credentials
        self.patcher_creds = patch('create_service_account.service_account.Credentials')
        self.mock_creds_class = self.patcher_creds.start()
        self.mock_creds = self.mock_creds_class.from_service_account_file.return_value
        self.mock_creds.with_subject.return_value = self.mock_creds
        self.mock_creds.token = "mock-token-from-file"

        # Patch os.path.exists for key file check
        self.patcher_exists = patch('os.path.exists')
        self.mock_exists = self.patcher_exists.start()
        # Default: key file exists unless mocked otherwise
        self.mock_exists.return_value = True

        # Patch pathlib.Path.home
        self.patcher_home = patch('pathlib.Path.home', return_value='/home/user')
        self.mock_home = self.patcher_home.start()

        # Patch time.sleep to speed up tests (synchronous)
        self.patcher_sleep = patch('time.sleep', new_callable=MagicMock)
        self.mock_sleep = self.patcher_sleep.start()

        # Patch datetime to control timestamp for project name
        self.fixed_now = datetime.datetime(2023, 1, 1, 12, 0, 0)
        self.patcher_datetime = patch('create_service_account.datetime')
        self.mock_datetime = self.patcher_datetime.start()
        self.mock_datetime.datetime.now.return_value = self.fixed_now
        # Side effect for time.time()
        self.patcher_time = patch('time.time', return_value=1672574400)
        self.mock_time = self.patcher_time.start()

    def tearDown(self):
        # Stop all patchers in reverse order
        self.patcher_time.stop()
        self.patcher_datetime.stop()
        self.patcher_sleep.stop()
        self.patcher_home.stop()
        self.patcher_exists.stop()
        self.patcher_creds.stop()
        self.patcher_request.stop()
        self.patcher_http.stop()
        self.patcher_subprocess.stop()
        self.patcher_os_system.stop()
        self.patcher_logging.stop()
        # self.patcher_stdout.stop()
        self.patcher_input.stop()

    def _setup_subprocess_mock(self):
        # Default behavior for subprocess mock
        def side_effect(command, **kwargs):
            process_mock = MagicMock()
            process_mock.returncode = 0
            process_mock.__enter__.return_value = process_mock

            # Default outputs
            out = b''
            err = b''

            if "gcloud config get-value project" in command:
                out = b'test-project-id\n'
            elif "gcloud iam service-accounts list" in command:
                if "uniqueId" in command:
                    out = b'1234567890\n'
                elif "email" in command:
                    out = b'sa-email@test-project-id.iam.gserviceaccount.com\n'
            elif "gcloud auth list" in command:
                out = b'admin@example.com\n'
            elif "gcloud organizations list" in command:
                out = b'123456789\n'
            elif "gcloud org-policies describe" in command:
                # Default to no enforcement to keep happy path simple
                out = b'enforce: false\n'
            elif "gcloud services enable" in command:
                # Check TOS
                out = b'operation-id'
            elif "sign-jwt" in command:
                out = b'signed-jwt-token\n'

            process_mock.communicate.return_value = (out, err)
            return process_mock

        self.mock_subprocess_popen.side_effect = side_effect

    def _setup_http_mock(self):
        def side_effect(url, method, body=None, headers=None):
            resp = MagicMock()
            resp.status = 200
            content = b'{}'

            if "oauth2.googleapis.com/token" in url:
                content = json.dumps({"access_token": "mock-access-token"}).encode()
            elif "admin/directory/v1/users" in url:
                # Admin SDK check
                content = json.dumps({"isAdmin": True}).encode()
            elif "calendar/v3/users/me/calendarList" in url:
                content = json.dumps({"kind": "calendar#calendarList"}).encode()
            elif "drive/v3/files" in url:
                content = json.dumps({"kind": "drive#fileList"}).encode()
            elif "gmail/v1/users/me/labels" in url:
                content = json.dumps({"labels": []}).encode()
            elif "tasks/v1/users/@me/lists" in url:
                content = json.dumps({"kind": "tasks#taskLists"}).encode()
            elif "people/v1/people/me/connections" in url:
                content = json.dumps({"connections": []}).encode()
            elif "contacts/a.com/full" in url: # Contacts API
                 # Contacts API XML/Atom feed simulation? The script just checks for error.
                 # Returning empty JSON is fine as long as it doesn't contain error.
                 content = b'{}'

            return resp, content

        self.mock_http_instance.request.side_effect = side_effect

    def test_run_gwm(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()

        with patch('sys.argv', ['create_service_account.py', '--tool', 'gwm']):
            create_service_account.main()

        # Verify gwm configuration
        self.assertEqual(create_service_account.TOOL_NAME, "GWM")
        self.assertIn("migrate.googleapis.com", create_service_account.APIS)

        # Verify commands
        # Fixed timestamp: 2023-01-01 12:00:00 -> 20230101-120000
        suffix = "-20230101-120000"
        project_name = f"GWM{suffix}"
        # Project ID lowercased
        project_id = project_name.lower()

        expected_cmd = f"gcloud projects create {project_id} --name '{project_name}' --set-as-default"

        self.assertTrue(any(expected_cmd in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

        # Verify specific GWM calls
        # APIs enabled?
        enable_calls = [call for call in self.mock_subprocess_popen.call_args_list if "gcloud services enable" in call[0][0]]
        self.assertTrue(len(enable_calls) > 0)

        # Service Account created?
        self.assertTrue(any("gcloud iam service-accounts create" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

        # Key created?
        self.assertTrue(any("gcloud iam service-accounts keys create" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

        # Downloaded?
        self.assertTrue(any("cloudshell download" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

        # Shredded?
        self.assertTrue(any("shred -u" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

    def test_run_gwmme(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()

        with patch('sys.argv', ['create_service_account.py', '--tool', 'gwmme']):
            create_service_account.main()

        self.assertEqual(create_service_account.TOOL_NAME, "GWMME")
        self.assertIn("groupsmigration.googleapis.com", create_service_account.APIS)

        # Verify GWMME usage of 'admin.googleapis.com' being first
        self.assertEqual(create_service_account.APIS[0], "admin.googleapis.com")

    def test_run_password_sync(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()

        with patch('sys.argv', ['create_service_account.py', '--tool', 'password_sync']):
            create_service_account.main()

        self.assertEqual(create_service_account.TOOL_NAME, "PasswordSync")
        self.assertEqual(create_service_account.APIS, ["admin.googleapis.com", "orgpolicy.googleapis.com"])

    def test_run_custom_tool(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()

        # Use --tool-name instead of --tool_name
        args = ['create_service_account.py',
                '--tool-name', 'CustomTool',
                '--apis', 'drive,calendar-json',
                '--scopes', 'https://www.googleapis.com/auth/drive,calendar']

        with patch('sys.argv', args):
            create_service_account.main()

        self.assertEqual(create_service_account.TOOL_NAME, "CustomTool")
        self.assertIn("drive.googleapis.com", create_service_account.APIS)
        self.assertIn("calendar-json.googleapis.com", create_service_account.APIS)
        self.assertIn("orgpolicy.googleapis.com", create_service_account.APIS)
        self.assertIn("https://www.googleapis.com/auth/calendar", create_service_account.SCOPES)

    def test_run_interactive_gwmme(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()

        # Simulate selecting 1 (GWMME) then enough Enters for the rest of the flow
        # 1: Welcome (Enter)
        # 2: Selection (1)
        # 3...N: Subsequent Enters
        # The first input call is "Welcome... Press Enter", so we give ''
        # The second input call is "Select the tool... Enter number", so we give '1'
        # Then subsequent prompts...
        self.mock_input.side_effect = itertools.chain(['', '1'], itertools.repeat(''))

        with patch('sys.argv', ['create_service_account.py']):
            create_service_account.main()

        self.assertEqual(create_service_account.TOOL_NAME, "GWMME")
        self.assertIn("admin.googleapis.com", create_service_account.APIS)

    def test_run_gwm_no_key(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()
        # Key file doesn't exist in no-key mode context for get_access_token_for_scopes
        self.mock_exists.return_value = False

        with patch('sys.argv', ['create_service_account.py', '--tool', 'gwm', '--no-key']):
            create_service_account.main()

        # Verify key file creation skipped
        self.assertFalse(any("gcloud iam service-accounts keys create" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        # Verify download skipped
        self.assertFalse(any("cloudshell download" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        # Verify shred skipped
        self.assertFalse(any("shred -u" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

        # Verify sign-jwt used
        self.assertTrue(any("gcloud iam service-accounts sign-jwt" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

        # Verify orgpolicy check skipped (default not in list for no-key unless added?)
        # Logic says: if not no_key: handle_org_policies()
        # So org-policies calls should be missing
        self.assertFalse(any("gcloud org-policies describe" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

        # Verify token creator role granted
        self.assertTrue(any("gcloud iam service-accounts add-iam-policy-binding" in call[0][0] and "roles/iam.serviceAccountTokenCreator" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

    def test_run_gwmme_no_key(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()
        self.mock_exists.return_value = False

        with patch('sys.argv', ['create_service_account.py', '--tool', 'gwmme', '--no-key']):
            create_service_account.main()

        self.assertFalse(any("gcloud iam service-accounts keys create" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        self.assertTrue(any("gcloud iam service-accounts sign-jwt" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        self.assertTrue(any("gcloud iam service-accounts add-iam-policy-binding" in call[0][0] and "roles/iam.serviceAccountTokenCreator" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

    def test_run_password_sync_no_key(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()
        self.mock_exists.return_value = False

        with patch('sys.argv', ['create_service_account.py', '--tool', 'password_sync', '--no-key']):
            create_service_account.main()

        self.assertFalse(any("gcloud iam service-accounts keys create" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        self.assertTrue(any("gcloud iam service-accounts sign-jwt" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        self.assertTrue(any("gcloud iam service-accounts add-iam-policy-binding" in call[0][0] and "roles/iam.serviceAccountTokenCreator" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

    def test_run_custom_tool_no_key(self):
        self._setup_subprocess_mock()
        self._setup_http_mock()
        self.mock_exists.return_value = False

        args = ['create_service_account.py',
                '--tool-name', 'CustomTool',
                '--apis', 'drive',
                '--scopes', 'drive',
                '--no-key']

        with patch('sys.argv', args):
            create_service_account.main()

        self.assertFalse(any("gcloud iam service-accounts keys create" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        self.assertTrue(any("gcloud iam service-accounts sign-jwt" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        self.assertTrue(any("gcloud iam service-accounts add-iam-policy-binding" in call[0][0] and "roles/iam.serviceAccountTokenCreator" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

    def test_enforced_org_policy(self):
        # Specific test where org policy is enforced
        def side_effect(command, **kwargs):
            process_mock = MagicMock()
            process_mock.returncode = 0
            process_mock.__enter__.return_value = process_mock
            out = b''
            err = b''

            if "gcloud config get-value project" in command:
                out = b'test-project-id\n'
            elif "gcloud org-policies describe iam.disableServiceAccountKeyCreation" in command:
                out = b'enforce: true\n'
            elif "gcloud org-policies describe" in command:
                out = b'enforce: false\n'
            elif "gcloud organizations get-iam-policy" in command:
                out = json.dumps({"bindings": []}).encode()
            elif "gcloud services enable" in command:
                out = b'op-id'
            elif "gcloud iam service-accounts list" in command:
                if "uniqueId" in command:
                    out = b'1234567890\n'
                elif "email" in command:
                    out = b'sa-email@test-project-id.iam.gserviceaccount.com\n'
            elif "gcloud auth list" in command:
                out = b'admin@example.com\n'
            elif "gcloud organizations list" in command:
                out = b'123456789\n'

            process_mock.communicate.return_value = (out, err)
            return process_mock

        self.mock_subprocess_popen.side_effect = side_effect
        self._setup_http_mock()

        # Need to simulate "Yes" input for granting role
        # Input sequence: Welcome (Enter) -> Grant Role (y) -> Authorize (Enter) -> API (Enter) -> Delete Key (Enter)
        # Note: Depending on where input() is called.
        # 1. Main Welcome -> ""
        # 2. Grant Role -> "y"
        # 3. Authorize -> ""
        # 4. Retry API? (if fails initially) - mockup always succeeds so no retry.
        # 5. Delete key -> ""
        self.mock_input.side_effect = ['', 'y', '', '', '', '']

        with patch('sys.argv', ['create_service_account.py', '--tool', 'gwm']):
            create_service_account.main()

        # Verify role was added
        self.assertTrue(any("gcloud organizations add-iam-policy-binding" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        # Verify policy was disabled
        self.assertTrue(any("gcloud resource-manager org-policies disable-enforce iam.disableServiceAccountKeyCreation" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))
        # Verify role was removed
        self.assertTrue(any("gcloud organizations remove-iam-policy-binding" in call[0][0] for call in self.mock_subprocess_popen.call_args_list))

if __name__ == '__main__':
    unittest.main()
