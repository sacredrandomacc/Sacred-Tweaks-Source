import json
import unittest
import urllib.request
import urllib.error
from desktop.overlay import OverlayServer

class FakeApi:
    def __init__(self): self.calls=[]
    def local(self, action, payload=None):
        self.calls.append(action)
        return {'ok':True,'data':{'enabled':False}}

class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.api=FakeApi();self.server=OverlayServer(self.api);self.pair=self.server.pair()
    def tearDown(self): self.server.close()
    def request(self, body, token=None, **headers):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.pair['port'])+'/command',json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+(token or self.pair['token']),**headers})
        return json.load(urllib.request.urlopen(req,timeout=3))
    def test_permitted_action_reaches_existing_boundary(self):
        self.request({'action':'emergency_stop'})
        self.assertEqual(self.api.calls,['emergency_stop'])
    def test_bad_token_and_browser_origin_rejected(self):
        for kwargs in ({'token':'wrong'}, {'Origin':'https://evil.example'}):
            with self.assertRaises(urllib.error.HTTPError) as e:self.request({'action':'macro_enable'},**kwargs)
            self.assertEqual(e.exception.code,403)
        self.assertEqual(self.api.calls,[])
    def test_rotation_revokes_previous_pair(self):
        old=self.pair['token'];self.pair=self.server.pair()
        with self.assertRaises(urllib.error.HTTPError):self.request({'action':'macro_status'},token=old)
    def test_arbitrary_actions_cannot_reach_api(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.request({'action':'export_recovery'})
        self.assertEqual(e.exception.code,400)
        self.assertEqual(self.api.calls,[])
