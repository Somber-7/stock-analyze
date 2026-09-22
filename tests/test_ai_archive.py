import copy
import unittest
from backend.ai.archive import build_snapshot, model_context


class ArchiveTests(unittest.TestCase):
    def test_research_is_in_model_input_once_and_raw_bars_stay_in_archive(self):
        source=dict(id='s',code='005930',url='https://example.com/a',content='unique evidence')
        context=dict(stocks=[dict(code='005930',daily=[dict(close=100)],raw_daily=[dict(close=100)])],
            web_research=dict(sources=[source],searches=[dict(query='q',sources=[source])]),
            benchmark=dict(daily=[dict(close=100)]),account='private',api_key='secret')
        original=copy.deepcopy(context)
        record=build_snapshot(dict(objective='review'),context,'system instructions')
        compact=model_context(record['context'])
        self.assertNotIn('sources',compact['web_research']['searches'][0])
        self.assertNotIn('raw_daily',compact['stocks'][0])
        self.assertIn('raw_daily',record['context']['stocks'][0])
        self.assertNotIn('private',str(record))
        self.assertNotIn('secret',str(record))
        self.assertEqual(context,original)
        self.assertEqual(len(record['sha256']),64)

    def test_snapshot_hash_changes_with_original_inputs_and_keeps_null(self):
        a=build_snapshot({},dict(stocks=[dict(code='005930',raw_daily=[dict(close=float('nan'))])]),'instructions')
        self.assertIsNone(a['context']['stocks'][0]['raw_daily'][0]['close'])
        b=build_snapshot({},dict(stocks=[]),'instructions')
        self.assertNotEqual(a['sha256'],b['sha256'])


if __name__=='__main__':unittest.main()
