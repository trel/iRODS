from __future__ import print_function

import os
import unittest

from . import session
from .. import lib
from ..configuration import IrodsConfig


class test_configurations(unittest.TestCase):
    plugin_name = IrodsConfig().default_rule_engine_plugin

    @classmethod
    def setUpClass(self):
        self.admin = session.mkuser_and_return_session('rodsadmin', 'otherrods', 'rods', lib.get_hostname())

        cfg = lib.open_and_load_json(
            os.path.join(IrodsConfig().irods_directory, 'test', 'test_framework_configuration.json'))
        self.auth_user = cfg['irods_authuser_name']
        self.auth_pass = cfg['irods_authuser_password']

        self.auth_session = session.mkuser_and_return_session('rodsuser', self.auth_user, self.auth_pass, lib.get_hostname())
        self.service_account_environment_file_path = os.path.join(
            os.path.expanduser('~'), '.irods', 'irods_environment.json')

        self.configuration_namespace = 'authentication'

    @classmethod
    def tearDownClass(self):
        self.auth_session.__exit__()

        self.admin.assert_icommand(['iadmin', 'rmuser', self.auth_session.username])
        self.admin.__exit__()
        with session.make_session_for_existing_admin() as admin_session:
            admin_session.assert_icommand(['iadmin', 'rmuser', self.admin.username])

    def do_test_invalid_password_time_configurations(self, _option_name):
        # Stash away the original configuration for later...
        original_config = self.admin.assert_icommand(
                ['iadmin', 'get_grid_configuration', self.configuration_namespace, _option_name], 'STDOUT')[1].strip()

        try:
            self.auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')
            self.auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

            for option_value in [' ', 'nope', str(-1), str(18446744073709552000), str(-18446744073709552000)]:
                with self.subTest(f'test with value [{option_value}]'):
                    self.admin.assert_icommand(
                        ['iadmin', 'set_grid_configuration', '--', self.configuration_namespace, _option_name, option_value])

                    # These invalid configurations will not cause any errors, but default values will be used.
                    self.auth_session.assert_icommand(
                        ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')
                    self.auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

        finally:
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, _option_name, original_config])

    def test_invalid_password_max_time(self):
        self.do_test_invalid_password_time_configurations('password_max_time')

    def test_invalid_password_min_time(self):
        self.do_test_invalid_password_time_configurations('password_min_time')

    def test_password_max_time_less_than_password_min_time_makes_ttl_constraints_unsatisfiable(self):
        min_time_option_name = 'password_min_time'
        max_time_option_name = 'password_max_time'

        # Stash away the original configuration for later...
        original_min_time = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, min_time_option_name], 'STDOUT')[1].strip()

        original_max_time = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, max_time_option_name], 'STDOUT')[1].strip()

        try:
            # Try a few different values here that are in the range of overall acceptable values:
            #     - 2 hours allows us to go up OR down by 1 hour (boundary case).
            #     - 336 hours is 1209600 seconds (or 2 weeks) which is the default maximum allowed TTL value.
            for base_ttl_in_hours in [2, 336]:
                with self.subTest(f'test with TTL of [{base_ttl_in_hours}] hours'):
                    base_ttl_in_seconds = base_ttl_in_hours * 3600

                    option_value = str(base_ttl_in_seconds + 10)
                    self.admin.assert_icommand(
                        ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, option_value])

                    # Set password_max_time to a value less than the password_min_time.
                    option_value = str(base_ttl_in_seconds - 10)
                    self.admin.assert_icommand(
                        ['iadmin', 'set_grid_configuration', self.configuration_namespace, max_time_option_name, option_value])

                    # Note: The min/max check does not occur when no TTL parameter is passed. If no TTL is passed, the
                    # password never expires (i.e. no TTL). Therefore, to test TTL lifetime configurations, we must pass
                    # TTL explicitly for each test. Even though this is native authentication,
                    # PAM_AUTH_PASSWORD_INVALID_TTL is the returned error.

                    # This is lower than the minimum and higher than the maximum. The TTL is invalid.
                    self.auth_session.assert_icommand(
                        ['iinit', '--ttl', str(base_ttl_in_hours)],
                         'STDERR', 'rcGetLimitedPassword failed with error [-994000]',
                         input=f'{self.auth_session.password}\n')

                    # This is lower than the maximum but also lower than the minimum. The TTL is invalid.
                    self.auth_session.assert_icommand(
                        ['iinit', '--ttl', str(base_ttl_in_hours - 1)],
                         'STDERR', 'rcGetLimitedPassword failed with error [-994000]',
                         input=f'{self.auth_session.password}\n')

                    # This is higher than the minimum but also higher than the maximum. The TTL is invalid.
                    self.auth_session.assert_icommand(
                        ['iinit', '--ttl', str(base_ttl_in_hours + 1)],
                         'STDERR', 'rcGetLimitedPassword failed with error [-994000]',
                         input=f'{self.auth_session.password}\n')

            # Restore grid configuration and try again, with success.
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, max_time_option_name, original_max_time])
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, original_min_time])

            self.auth_session.assert_icommand(
                ['iinit', '--ttl', str(1)], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')
            self.auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

        finally:
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, max_time_option_name, original_max_time])
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, original_min_time])

    @unittest.skip('iinit does not allow TTL to be under 1 hour for native authentication. Skip this test for now.')
    def test_password_expires_appropriately_based_on_grid_configuration_value(self):
        import time

        min_time_option_name = 'password_min_time'
        max_time_option_name = 'password_max_time'

        # Stash away the original configuration for later...
        original_min_time = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, min_time_option_name], 'STDOUT')[1].strip()

        original_max_time = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, max_time_option_name], 'STDOUT')[1].strip()

        try:
            # When no TTL is specified, the default value is the minimum password lifetime as configured in
            # R_GRID_CONFIGURATION. This value should be higher than 3 seconds to ensure steps in the test
            # have enough time to complete.
            ttl = 4
            self.assertGreater(ttl, 3)
            option_value = str(ttl)
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, option_value])

            # Authenticate and run a command...
            self.auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')

            self.auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

            # Sleep until the password is expired...
            time.sleep(ttl + 1)

            # Password should be expired now...
            self.auth_session.assert_icommand(["ils"], 'STDERR', 'CAT_PASSWORD_EXPIRED: failed to perform request')

            # ...and stays expired.
            # TODO: irods/irods#7344 - This should emit a better error message.
            self.auth_session.assert_icommand(["ils"], 'STDERR', 'CAT_INVALID_AUTHENTICATION: failed to perform request')

            # Restore grid configuration and try again, with success.
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, max_time_option_name, original_max_time])
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, original_min_time])

            self.auth_session.assert_icommand(['iinit'], 'STDOUT', input=f'{self.auth_session.password}\n')
            self.auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

        finally:
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, max_time_option_name, original_max_time])
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, original_min_time])

            # Re-authenticate as the session user to make sure things can be cleaned up.
            self.auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')

    @unittest.skip('password_extend_lifetime is not supported for native authentication.')
    def test_password_extend_lifetime_set_to_true_extends_other_authentications_past_expiration(self):
        import time

        min_time_option_name = 'password_min_time'
        extend_lifetime_option_name = 'password_extend_lifetime'

        # Stash away the original configuration for later...
        original_min_time = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, min_time_option_name],
            'STDOUT')[1].strip()

        original_extend_lifetime = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, extend_lifetime_option_name],
            'STDOUT')[1].strip()

        # Set password_extend_lifetime to 1 so that the same randomly generated password is used for all sessions.
        self.admin.assert_icommand(
            ['iadmin', 'set_grid_configuration', self.configuration_namespace, extend_lifetime_option_name, '1'])

        # Make a new session of the existing auth_user. The data is "managed" in the session, so the session
        # collection shall be shared with the other session.
        temp_auth_session = session.make_session_for_existing_user(
            self.auth_user, self.auth_pass, lib.get_hostname(), self.auth_session.zone_name)
        temp_auth_session.assert_icommand(['icd', self.auth_session.session_collection])

        try:
            # Set the minimum time to a very short value so that the password expires in a reasonable amount of
            # time for testing purposes. This value should be higher than 3 seconds to ensure steps in the test
            # have enough time to complete.
            ttl = 4
            self.assertGreater(ttl, 3)
            option_value = str(ttl)
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, option_value])

            # Authenticate with both sessions and run a command...
            self.auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')
            temp_auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')

            self.auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)
            temp_auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

            # Sleep until just before password is expired...
            time.sleep(ttl - 1)

            # Re-authenticate as one of the sessions such that the random password lifetime is extended. This
            # will allow the other session to continue without re-authenticating.
            self.auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')

            # We want to sleep 1 second past the timeout (ttl + 1) to ensure that the original expiration time
            # has passed. We already slept ttl - 1 seconds, so the remaining time is calculated like this:
            # remaining_sleep_time = total_time_to_sleep - time_already_slept = (ttl + 1) - (ttl - 1) = 2
            time.sleep(2)

            # Run a command as the other session to show that the existing password is still valid.
            temp_auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

            # The re-authenticated session should also be able to run commands, of course.
            self.auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

            # Sleep again to let the password time out.
            time.sleep(ttl + 1)

            # Password should be expired now...
            temp_auth_session.assert_icommand(
                ["ils"], 'STDERR', 'CAT_PASSWORD_EXPIRED: failed to perform request')
            # The sessions are using the same password, so the second response will be different
            # TODO: irods/irods#7344 - This should emit a better error message.
            self.auth_session.assert_icommand(
                ["ils"], 'STDERR', 'CAT_INVALID_AUTHENTICATION: failed to perform request')

        finally:
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, extend_lifetime_option_name, original_extend_lifetime])
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, original_min_time])

            # Re-authenticate as the session user to make sure things can be cleaned up.
            self.auth_session.assert_icommand(['iinit'], 'STDOUT', input=f'{self.auth_session.password}\n')

    @unittest.skip('password_extend_lifetime is not supported for native authentication.')
    def test_password_extend_lifetime_set_to_false_invalidates_other_authentications_on_expiration(self):
        import time

        min_time_option_name = 'password_min_time'
        extend_lifetime_option_name = 'password_extend_lifetime'

        # Stash away the original configuration for later...
        original_min_time = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, min_time_option_name],
            'STDOUT')[1].strip()

        original_extend_lifetime = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, extend_lifetime_option_name],
            'STDOUT')[1].strip()

        # Set password_extend_lifetime to 1 so that the same randomly generated password is used for all sessions.
        self.admin.assert_icommand(
            ['iadmin', 'set_grid_configuration', self.configuration_namespace, extend_lifetime_option_name, '1'])

        # Make a new session of the existing auth_user. The data is "managed" in the session, so the session
        # collection shall be shared with the other session.
        temp_auth_session = session.make_session_for_existing_user(
            self.auth_user, self.auth_pass, lib.get_hostname(), self.auth_session.zone_name)
        temp_auth_session.assert_icommand(['icd', self.auth_session.session_collection])

        try:
            # Set the minimum time to a very short value so that the password expires in a reasonable amount of
            # time for testing purposes. This value should be higher than 3 seconds to ensure steps in the test
            # have enough time to complete.
            ttl = 4
            self.assertGreater(ttl, 3)
            option_value = str(ttl)
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, option_value])

            # Authenticate with both sessions and run a command...
            self.auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')
            temp_auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{temp_auth_session.password}\n')

            self.auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)
            temp_auth_session.assert_icommand(["ils"], 'STDOUT', self.auth_session.session_collection)

            # Disable password_extend_lifetime so that on the next authentication, the expiration time of the
            # existing password will not be extended.
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, extend_lifetime_option_name, '0'])

            # Sleep until just before password is expired...
            time.sleep(ttl - 1)

            # Re-authenticate as one of the sessions - the random password lifetime will not be extended for
            # either session.
            self.auth_session.assert_icommand(
                ['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')

            # We want to sleep 1 second past the timeout (ttl + 1) to ensure that the original expiration time
            # has passed. We already slept ttl - 1 seconds, so the remaining time is calculated like this:
            # remaining_sleep_time = total_time_to_sleep - time_already_slept = (ttl + 1) - (ttl - 1) = 2
            time.sleep(2)

            # Password should be expired for both sessions despite one having re-authenticated past the
            # expiry time.
            temp_auth_session.assert_icommand(
                ["ils"], 'STDERR', 'CAT_PASSWORD_EXPIRED: failed to perform request')
            # The sessions are using the same password, so the second response will be different
            # TODO: irods/irods#7344 - This should emit a better error message.
            self.auth_session.assert_icommand(
                ["ils"], 'STDERR', 'CAT_INVALID_AUTHENTICATION: failed to perform request')

        finally:
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, extend_lifetime_option_name, original_extend_lifetime])
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, min_time_option_name, original_min_time])

            # Re-authenticate as the session user to make sure things can be cleaned up.
            self.auth_session.assert_icommand(['iinit'], 'STDOUT', 'iRODS password', input=f'{self.auth_session.password}\n')

    def test_password_max_time_can_exceed_1209600__issue_3742_5096(self):
        # Note: This does NOT test the TTL as this would require waiting for the password to expire (2 weeks + 1 hour).
        # The test is meant to ensure that a TTL greater than 1209600 is allowed with iinit when it is so configured.

        max_time_option_name = 'password_max_time'

        # Stash away the original configuration for later...
        original_max_time = self.admin.assert_icommand(
            ['iadmin', 'get_grid_configuration', self.configuration_namespace, max_time_option_name], 'STDOUT')[1].strip()

        try:
            # The test value is 2 hours more than the default in order to try a TTL value 1 greater and 1 less than the
            # configured password_max_time while still remaining above 1209600 to show that there is nothing special
            # about that value.
            base_ttl_in_hours = 336 + 2
            base_ttl_in_seconds = base_ttl_in_hours * 3600

            # Set password_max_time to the value for the test.
            option_value = str(base_ttl_in_seconds)
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, max_time_option_name, option_value])

            # Note: The min/max check does not occur when no TTL parameter is passed. If no TTL is passed, the
            # password never expires (i.e. no TTL). Therefore, to test TTL lifetime configurations, we must pass
            # TTL explicitly for each test. Even though this is native authentication,
            # PAM_AUTH_PASSWORD_INVALID_TTL is the returned error.

            # TTL value is higher than the maximum. The TTL is invalid.
            self.auth_session.assert_icommand(
                ['iinit', '--ttl', str(base_ttl_in_hours + 1)],
                 'STDERR', 'rcGetLimitedPassword failed with error [-994000]',
                 input=f'{self.auth_session.password}\n')

            # TTL value is lower than the maximum. The TTL is valid.
            self.auth_session.assert_icommand(
                 ['iinit', '--ttl', str(base_ttl_in_hours - 1)],
                 'STDOUT', 'Enter your current iRODS password',
                 input=f'{self.auth_session.password}\n')

            # TTL value is equal to the maximum. The TTL is valid.
            self.auth_session.assert_icommand(
                 ['iinit', '--ttl', str(base_ttl_in_hours)],
                 'STDOUT', 'Enter your current iRODS password',
                 input=f'{self.auth_session.password}\n')

        finally:
            self.admin.assert_icommand(
                ['iadmin', 'set_grid_configuration', self.configuration_namespace, max_time_option_name, original_max_time])
