import json
import unittest

from desktop.profile_transfer import FORMAT, encode_profile_bundle, validate_profile_bundle
from desktop.macros import DEFAULT_CONFIG


class ProfileTransferTests(unittest.TestCase):
    def test_export_round_trip(self):
        profile={'name':'Builder','config':{'kind':'single_edit','config':dict(DEFAULT_CONFIG)}}
        result=validate_profile_bundle(encode_profile_bundle([profile]))
        self.assertEqual(result,[profile])

    def test_rejects_oversize_unknown_and_invalid_profile(self):
        for payload in (b'x'*1_000_001,
                        json.dumps({'format':FORMAT,'version':1,'profiles':[{'name':'x','config':{},'script':'bad'}]}).encode(),
                        json.dumps({'format':FORMAT,'version':1,'profiles':[{'name':'x','config':{'kind':'single_edit','config':{'script':'bad'}}}]}).encode()):
            with self.subTest(size=len(payload)):
                with self.assertRaises(ValueError): validate_profile_bundle(payload)

    def test_import_is_data_only_and_does_not_enable_configuration(self):
        # No executable/script field is accepted; only validated configuration data is returned.
        profile={'name':'Safe','config':{'kind':'single_edit','config':dict(DEFAULT_CONFIG)}}
        clean=validate_profile_bundle(encode_profile_bundle([profile]))
        self.assertNotIn('enabled',clean[0]['config'])
        self.assertNotIn('script',clean[0]['config']['config'])


if __name__=='__main__':
    unittest.main()
