import copy
import json
import unittest
from pathlib import Path

from bot import compose
from reply_logic import process_reply
import server

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'expanded'


def fixture(test_id):
    pair = next(p for p in json.loads((DATA / 'test_pairs.json').read_text())['pairs'] if p['test_id'] == test_id)
    def load(folder, key):
        return json.loads((DATA / folder / (key + '.json')).read_text())
    t = load('triggers', pair['trigger_id'])
    m = load('merchants', pair['merchant_id'])
    c = load('customers', pair['customer_id']) if pair.get('customer_id') else None
    return load('categories', m['category_slug']), m, t, c


def state(kind='perf_spike'):
    return {'c': {'merchant_id': 'm', 'customer_id': None, 'last_turn': 1, 'trigger_kind': kind,
                  'topic': 'corporate_bulk_thali_package'}}


def reply(states, message, turn=2, role='merchant'):
    return process_reply({'conversation_id':'c', 'merchant_id':'m', 'customer_id':None,
                          'from_role':role, 'turn_number':turn, 'message':message}, states)


class RegressionTests(unittest.TestCase):
    def setUp(self):
        server.CONTEXTS.clear(); server.SENT.clear(); server.CONVERSATIONS.clear()

    def test_original_coverage(self):
        pairs = json.loads((DATA / 'test_pairs.json').read_text())['pairs']
        skipped = {p['test_id'] for p in pairs if not compose(*fixture(p['test_id']))}
        self.assertEqual(skipped, {'T03','T04','T08','T10','T12','T14','T15','T18','T19','T23','T25','T29'})

    def test_role_and_identity(self):
        self.assertEqual(reply(state(), 'yes', role='customer')['action'], 'end')
        k,m,t,c = fixture('T17');t['merchant_id']='different'
        self.assertEqual(compose(k,m,t,c), {})

    def test_reply_intents(self):
        for text, action in [('No problem','send'),('No thanks','end'),('Not sure','wait'),('Please explain the price','wait'),('No problem, but not interested','end')]:
            with self.subTest(text=text): self.assertEqual(reply(state(),text)['action'],action)

    def test_auto_replies(self):
        s=state()
        self.assertEqual([reply(s,'Automatic reply: out of office',t)['action'] for t in (2,3,4)], ['wait','wait','end'])

    def test_optout_is_persistent(self):
        s=state()
        self.assertEqual(reply(s,'Stop messaging me')['action'],'end')
        self.assertTrue(s['c']['opted_out'])
        self.assertEqual(reply(s,'yes',3)['action'],'end')
        server.CONVERSATIONS.update(s)
        server.CONTEXTS[('category','cat')]={'payload':{}}
        server.CONTEXTS[('merchant','m')]={'payload':{'merchant_id':'m','category_slug':'cat'}}
        server.CONTEXTS[('trigger','t')]={'payload':{'id':'t','scope':'merchant','merchant_id':'m','kind':'perf_spike','payload':{'metric':'calls','delta_pct':.1,'window':'7d'}}}
        self.assertEqual(server.process_tick({'now':'2026-04-26T00:00:00Z','available_triggers':['t']})['actions'],[])

    def test_duplicate_turn(self):
        s=state(); first=reply(s,'yes')
        self.assertEqual(first['action'],'send')
        self.assertEqual(reply(s,'yes')['action'],'wait')

    def test_no_repeat_draft(self):
        s=state(); first=reply(s,'yes')
        self.assertIn('Review checklist:', first['body'])
        self.assertEqual(reply(s,'yes',3)['action'],'wait')

    def test_planning_price(self):
        result=reply(state('active_planning_intent'),'199')
        self.assertIn('₹199 per head',result['body'])
        self.assertIn('[confirm',result['body'])

    def test_recall_minutes_and_zone(self):
        k,m,t,c=fixture('T28');t['payload']['available_slots']=[{'iso':'2026-11-05T18:45:00+05:30'}]
        body=compose(k,m,t,c)['body']
        self.assertIn('06:45 PM',body);self.assertIn('UTC+05:30',body)

    def test_revoked_consent(self):
        k,m,t,c=fixture('T28');c['consent']['revoked_at']='2026-04-25'
        self.assertEqual(compose(k,m,t,c),{})

    def test_wrong_performance_direction(self):
        k,m,t,c=fixture('T24');t['payload']['delta_pct']=.2
        self.assertEqual(compose(k,m,t,c),{})

    def test_timezone_expiry_and_tick_reply(self):
        k,m,t,c=fixture('T26');t['expires_at']='2026-04-26T11:00:00+05:30'
        for scope,key,payload in [('category',m['category_slug'],k),('merchant',m['merchant_id'],m),('trigger',t['id'],t)]:
            server.CONTEXTS[(scope,key)]={'payload':payload}
        self.assertEqual(server.process_tick({'now':'2026-04-26T06:00:00Z','available_triggers':[t['id']]})['actions'],[])
        actions=server.process_tick({'now':'2026-04-26T05:00:00Z','available_triggers':[t['id']]})['actions']
        self.assertEqual(len(actions),1)
        response=process_reply({'conversation_id':actions[0]['conversation_id'],'merchant_id':m['merchant_id'],'customer_id':None,'from_role':'merchant','turn_number':1,'message':'yes'},server.CONVERSATIONS)
        self.assertIn('Review checklist',response['body'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
