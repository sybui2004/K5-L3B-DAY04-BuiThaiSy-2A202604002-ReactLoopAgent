"""In trace của một kết quả run_agent/run.py cho dễ đọc khi demo.

Dùng: python docs/demo/show_trace.py ket_qua.json
Hoặc: python run.py "câu hỏi" | python docs/demo/show_trace.py
"""
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
raw = open(sys.argv[1], encoding='utf-8').read() if len(sys.argv) > 1 else sys.stdin.read()
run = json.loads(raw)

print(f"status: {run['status']}" + (f"  error: {run['error']}" if run.get('error') else ''))
for e in run['trace']:
    kind = e['event']
    if kind == 'model':
        print(f"[step {e['step']}] model finish={e['finish']} tool_calls={e['tool_calls']}")
    elif kind == 'tool':
        result = json.dumps(e['result'], ensure_ascii=False)
        print(f"[step {e['step']}] TOOL {e['name']} args={json.dumps(e['arguments'], ensure_ascii=False)}")
        print(f"          -> {result[:160]}{'...' if len(result) > 160 else ''}")
    else:
        print(f"[step {e.get('step', '-')}] {kind.upper()} {e.get('message', '')}")
print('\nANSWER:\n' + run['answer'])
