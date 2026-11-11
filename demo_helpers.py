"""Hàm thuần cho trace viewer (không import streamlit nên test offline được)."""
import json
import re
import time
from pathlib import Path

DETAIL_LIMIT = 300
KEY_ENV = {'openai': 'OPENAI_API_KEY', 'gemini': 'GEMINI_API_KEY',
           'anthropic': 'ANTHROPIC_API_KEY', 'openrouter': 'OPENROUTER_API_KEY'}
_URL = re.compile(r'https?://[^\s)\]>"\'`]+')


def load_results(path):
    """Đọc file eval; trả None nếu chưa có file hoặc file hỏng."""
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def case_ids(results):
    return [c.get('id', '?') for c in (results or {}).get('cases', [])]


def get_case(results, case_id):
    for case in (results or {}).get('cases', []):
        if case.get('id') == case_id:
            return case
    return None


def urls_in(text):
    return sorted({u.rstrip('.,;:') for u in _URL.findall(text or '')})


def _short(value, limit=DETAIL_LIMIT):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + '...'


def trace_rows(trace):
    """Mỗi event -> một dòng hiển thị: step, event, title, detail (rút gọn), is_error, raw."""
    rows = []
    for item in trace or []:
        if not isinstance(item, dict):
            rows.append({'step': None, 'event': '?', 'title': 'Event không hợp lệ',
                         'detail': _short(item), 'is_error': False, 'raw': item})
            continue
        event, step = item.get('event', '?'), item.get('step')
        if event == 'model':
            title = f"Model quyết định: {item.get('finish')}"
            detail = f"{item.get('tool_calls', 0)} tool call"
            is_error = False
        elif event == 'tool':
            result = item.get('result')
            is_error = isinstance(result, dict) and result.get('ok') is False
            title = f"Tool: {item.get('name')}"
            detail = f"args={_short(item.get('arguments'), 120)} -> {_short(result)}"
        elif event == 'validation_missing_source':
            title, detail, is_error = 'Cổng nguồn: answer thiếu URL, yêu cầu bổ sung', '', False
        elif event == 'error':
            title, detail, is_error = 'Lỗi kết thúc run', _short(item.get('message', '')), True
        else:
            title, detail, is_error = f'Event: {event}', _short({k: v for k, v in item.items() if k != 'event'}), False
        rows.append({'step': step, 'event': event, 'title': title, 'detail': detail,
                     'is_error': is_error, 'raw': item})
    return rows


def summarize_run(result, grade=None):
    result = result or {}
    trace = [t for t in result.get('trace', []) if isinstance(t, dict)]
    tools = [t for t in trace if t.get('event') == 'tool']
    tokens = 0
    for u in result.get('usage', []):
        if isinstance(u, dict):
            tokens += (u.get('input_tokens') or u.get('prompt_tokens') or 0) \
                + (u.get('output_tokens') or u.get('completion_tokens') or 0)
    grade = grade or {}
    return {
        'status': result.get('status'),
        'score': grade.get('score'),
        'grade_status': grade.get('status'),
        'model_calls': sum(1 for t in trace if t.get('event') == 'model'),
        'tool_calls': len(tools),
        'tool_errors': sum(1 for t in tools if isinstance(t.get('result'), dict) and t['result'].get('ok') is False),
        'total_tokens': tokens,
        'urls': urls_in(result.get('answer', '')),
    }


def live_env_status(env):
    """(sẵn_sàng, danh_sách_biến_còn_thiếu) cho tab chạy live."""
    missing = [name for name in ('PROVIDER', 'MODEL') if not env.get(name)]
    provider = env.get('PROVIDER')
    if provider in KEY_ENV and not env.get(KEY_ENV[provider]):
        missing.append(KEY_ENV[provider])
    elif provider and provider not in KEY_ENV:
        missing.append(f'PROVIDER hợp lệ (một trong {", ".join(KEY_ENV)})')
    return not missing, missing


def save_run(question, result, directory='demo_runs', meta=None):
    """Lưu một lần chạy live; chỉ ghi các field an toàn (không ghi env/header).

    `meta` (tuỳ chọn): nhãn mô tả run, ví dụ {'toolset','scenario','label'}.
    """
    safe = {k: result.get(k) for k in ('status', 'answer', 'trace', 'usage', 'error') if k in result}
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"run_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1000000:06d}.json"
    payload = {'question': question, 'result': safe}
    if meta:
        payload['meta'] = {k: meta[k] for k in ('sample_id', 'label', 'shows', 'toolset', 'scenario', 'simulated', 'inject_text') if k in meta}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def list_runs(directory='demo_runs'):
    folder = Path(directory)
    return sorted(folder.glob('run_*.json'), reverse=True) if folder.is_dir() else []
