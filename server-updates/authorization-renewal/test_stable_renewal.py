import unittest

from smoke_stable_renewal import APP, VerificationError, license_payload


class RenewalEnvelopeTests(unittest.TestCase):
    def test_activation_envelope_uses_current_operation_grant(self):
        # The nested license retains the original grant; already-bound responses
        # deliberately override that at the top level with zero new points.
        result = license_payload({'ok': True, 'action': 'already_bound', 'grant_score': 0,
            'license': {'app_name': APP, 'code_id': 'TEST', 'grant_score': 100}})
        self.assertEqual(result['grant_score'], 0)
        self.assertEqual(result['code_id'], 'TEST')

    def test_status_remains_top_level(self):
        self.assertEqual(license_payload({'ok': True, 'app_name': APP, 'remaining_credits': 0})['remaining_credits'], 0)

    def test_conflicting_identity_is_rejected(self):
        with self.assertRaises(VerificationError):
            license_payload({'ok': True, 'code_id': 'A', 'license': {'app_name': APP, 'code_id': 'B'}})

    def test_wrong_application_and_echo_payload_are_rejected(self):
        for body in ({'ok': True, 'app_name': 'different-app'}, {'ok': True, 'data': {'app_name': APP}}):
            with self.assertRaises(VerificationError):
                license_payload(body)


if __name__ == '__main__':
    unittest.main()
