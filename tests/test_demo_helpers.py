import json
import tempfile
import unittest
from pathlib import Path

import demo_helpers as h


def sample_result():
    return {
        'status': 'completed',
        'answer': 'Không có sự cố. Nguồn: https://www.githubstatus.com/incidents/abc.',
        'trace': [
            {'event': 'model', 'step': 1, 'finish': 'tool_calls', 'tool_calls': 2},
            {'event': 'tool', 'step': 1, 'name': 'get_status', 'arguments': {'provider': 'github'},
             'result': {'ok': True, 'incidents': []}},
            {'event': 'tool', 'step': 1, 'name': 'get_incident_details', 'arguments': {'id': 'x'},
             'result': {'ok': False, 'error': 'NOT_FOUND'}},
            {'event': 'model', 'step': 2, 'finish': 'stop', 'tool_calls': 0},
        ],
        'usage': [{'input_tokens': 10, 'output_tokens': 5}, {'input_tokens': 20, 'output_tokens': 7}],
    }


class TraceRowsTests(unittest.TestCase):
    def test_failed_tool_marked_as_error(self):
        rows = h.trace_rows(sample_result()['trace'])
        tools = [r for r in rows if r['event'] == 'tool']
        self.assertFalse(tools[0]['is_error'])
        self.assertTrue(tools[1]['is_error'])

    def test_validation_and_error_events_shown(self):
        rows = h.trace_rows([
            {'event': 'validation_missing_source', 'step': 2},
            {'event': 'error', 'step': 3, 'message': 'boom'},
        ])
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0]['is_error'])
        self.assertTrue(rows[1]['is_error'])
        self.assertIn('boom', rows[1]['detail'])

    def test_unknown_event_does_not_crash(self):
        rows = h.trace_rows([{'event': 'lạ', 'step': 1}, {'khong_co_event': 1}, 'rác'])
        self.assertEqual(len(rows), 3)

    def test_long_result_is_shortened_but_kept_in_full(self):
        big = {'event': 'tool', 'step': 1, 'name': 't', 'arguments': {}, 'result': {'ok': True, 'x': 'a' * 2000}}
        row = h.trace_rows([big])[0]
        self.assertLess(len(row['detail']), 2 * h.DETAIL_LIMIT)  # args + result đều đã rút gọn
        self.assertTrue(row['detail'].endswith('...'))
        self.assertEqual(row['raw'], big)


class SummaryTests(unittest.TestCase):
    def test_counts_calls_tokens_and_urls(self):
        s = h.summarize_run(sample_result())
        self.assertEqual(s['model_calls'], 2)
        self.assertEqual(s['tool_calls'], 2)
        self.assertEqual(s['tool_errors'], 1)
        self.assertEqual(s['total_tokens'], 42)
        self.assertEqual(s['urls'], ['https://www.githubstatus.com/incidents/abc'])

    def test_empty_result(self):
        s = h.summarize_run({})
        self.assertEqual((s['model_calls'], s['tool_calls'], s['total_tokens']), (0, 0, 0))


class LoadTests(unittest.TestCase):
    def test_load_and_lookup(self):
        report = {'summary': {}, 'config': {}, 'cases': [{'id': 'E1', 'question': 'q', 'result': {}, 'grade': {}}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'e.json'
            p.write_text(json.dumps(report), encoding='utf-8')
            loaded = h.load_results(p)
        self.assertEqual(h.case_ids(loaded), ['E1'])
        self.assertEqual(h.get_case(loaded, 'E1')['question'], 'q')
        self.assertIsNone(h.get_case(loaded, 'ZZ'))

    def test_missing_file_returns_none(self):
        self.assertIsNone(h.load_results('khong_ton_tai.json'))


class LiveTests(unittest.TestCase):
    def test_env_ready_requires_provider_model_and_key(self):
        ok, missing = h.live_env_status({})
        self.assertFalse(ok)
        self.assertIn('PROVIDER', missing)
        ok, missing = h.live_env_status({'PROVIDER': 'anthropic', 'MODEL': 'm'})
        self.assertFalse(ok)
        self.assertEqual(missing, ['ANTHROPIC_API_KEY'])
        ok, missing = h.live_env_status({'PROVIDER': 'anthropic', 'MODEL': 'm', 'ANTHROPIC_API_KEY': 'k'})
        self.assertTrue(ok)

    def test_save_run_keeps_only_safe_fields(self):
        result = sample_result()
        result['api_key'] = 'sk-secret'
        with tempfile.TemporaryDirectory() as d:
            path = h.save_run('câu hỏi', result, d)
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('sk-secret', text)
            data = json.loads(text)
            self.assertEqual(data['question'], 'câu hỏi')
            self.assertEqual(data['result']['status'], 'completed')
            self.assertEqual(len(h.list_runs(d)), 1)

    def test_list_runs_missing_dir(self):
        self.assertEqual(h.list_runs('khong_ton_tai_dir'), [])


if __name__ == '__main__':
    unittest.main()
