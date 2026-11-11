"""Chạy sẵn các câu mẫu và lưu vào demo_runs/ để mở lại trong tab "Chạy live" mà không tốn thời gian chờ.

Dùng (biến PROVIDER/MODEL/API key phải có trong terminal, script không đọc .env):
    python demo_prerun.py              # chạy các câu mẫu chưa có run
    python demo_prerun.py --only B3 B4 # chỉ chạy một số câu
    python demo_prerun.py --force      # chạy lại, lưu thêm run mới
"""
import argparse
import json
import sys

import demo_helpers as h
from demo_runner import run_demo, run_scripted
from demo_samples import SAMPLES, SCRIPTED

RUN_DIR = 'demo_runs'


def saved_sample_ids(directory=RUN_DIR):
    ids = set()
    for path in h.list_runs(directory):
        try:
            meta = json.loads(path.read_text(encoding='utf-8')).get('meta') or {}
        except (OSError, ValueError):
            continue
        if meta.get('sample_id'):
            ids.add(meta['sample_id'])
    return ids


def _question(demo_id):
    return {'G1': 'Kiểm tra npm status và cho tôi tình trạng tổng quan cùng nguồn.',
            'G2': 'Kiểm tra incident GitHub xr3myzj7ms51 và dẫn nguồn.'}[demo_id]


def main(argv=None):
    p = argparse.ArgumentParser(description='Chạy sẵn câu mẫu demo')
    p.add_argument('--only', nargs='*', help='ID câu mẫu cần chạy (ví dụ B3 B4 G1)')
    p.add_argument('--force', action='store_true', help='chạy lại cả câu đã có run')
    args = p.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    done = set() if args.force else saved_sample_ids()
    wanted = lambda s: (not args.only or s['id'] in args.only) and s['id'] not in done  # noqa: E731
    todo = [s for s in SAMPLES if wanted(s)]
    for s in todo:
        result = run_demo(s['question'], s['toolset'], s['scenario'], inject_text=s.get('inject_text'))
        h.save_run(s['question'], result, RUN_DIR, meta={**s, 'sample_id': s['id']})
        tools = sum(e['event'] == 'tool' for e in result['trace'])
        print(f"{s['id']:>3} {result['status']:<10} tool_calls={tools:<2} {s['label']}")
    scripted = [s for s in SCRIPTED if wanted(s)]  # demo mô phỏng: không gọi LLM, không tốn token
    for s in scripted:
        result = run_scripted(s['id'])
        h.save_run(_question(s['id']), result, RUN_DIR,
                   meta={**s, 'sample_id': s['id'], 'simulated': True})
        print(f"{s['id']:>3} {result['status']:<10} (mô phỏng) {s['label']}")
    todo = todo + scripted
    if not todo:
        print('Không có câu mẫu nào cần chạy (dùng --force để chạy lại).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
