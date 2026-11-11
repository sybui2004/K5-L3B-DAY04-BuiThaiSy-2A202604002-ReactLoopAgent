# Status Investigation Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện `run_agent` (ReAct loop), chạy eval 22 case trước/sau một cải tiến có evidence, viết `NOTES.md`, và (tuỳ chọn) làm bonus 5 provider.

**Architecture:** Một hàm `run_agent` trong `agent.py` lặp: gọi `provider.complete` → append assistant message nguyên vẹn → thực thi mọi tool call → append tool result theo `tool_call_id` → lặp tới `stop`/lỗi/hết `max_steps`. Các helper nhỏ (`_parse_args`, `_safe_execute`, `_urls_in`) giữ vòng lặp dễ đọc. Cải tiến Bài 4 là cổng kiểm tra nguồn (URL) trước khi chấp nhận final answer.

**Tech Stack:** Python 3.10+ stdlib, `unittest`, `evals/run_evals.py`, provider adapter có sẵn trong `providers.py`.

**Spec:** `docs/superpowers/specs/2026-11-11-react-loop-agent-spec.md`

## Global Constraints

- Không dùng LangChain/LangGraph hay framework agent; chỉ stdlib.
- Chỉ sửa `agent.py`, `NOTES.md`, file kết quả eval (+ docs). KHÔNG sửa `fixtures/`, `evals/cases.json`, `evals/scenarios.py`, `evals/grading.py`, rubric, `tests/`; không sửa tay kết quả eval.
- Trace: mỗi phần tử có key `event`; tool call đúng dạng `{'event':'tool','step':n,'name':...,'arguments':...,'result':...}`; không ghi API key.
- Tool result message đúng `{'role':'tool','tool_call_id':id,'content':json_string}`.
- `eval_before.json` và `eval_after.json`: cùng provider, model, judge, snapshot, `--max-steps`, dataset; `summary.score_0_100` ≠ null.
- CLAUDE.md người dùng: **không tự commit**; chỉ commit khi được yêu cầu, và không thêm `Co-Authored-By`. Các bước "Commit" dưới đây chỉ thực hiện khi người dùng đồng ý.
- Windows: dùng `python` (không phải `python3`); đặt biến bằng `$env:PROVIDER='...'`.

## Review Focus

1. Một response có 2+ tool calls, trong đó 1 call JSON lỗi: cả hai đều phải nhận tool message đúng ID (Task 1–2).
2. `arguments` là JSON hợp lệ nhưng không phải object (vd `"[]"`, `"null"`): phải trả `INVALID_ARGUMENTS`, không crash (Task 2).
3. `tools.execute` ném exception bất ngờ hoặc kết quả không JSON-serialize được: trở thành observation, không crash (Task 2).
4. `provider.complete` ném exception / `finish` lạ (`content_filter`): `status='error'`, không `completed` (Task 2).
5. Model trả final answer rỗng, hoặc URL trong answer chỉ là URL của incident không-quan-sát: vẫn bị coi là thiếu nguồn; không bắt URL khi chưa có incident thành công (Task 3).

---

### Task 1: Agent loop cốt lõi

**Files:**
- Modify: `agent.py` (thay thân `run_agent`, giữ nguyên `SYSTEM_PROMPT`)
- Test: `tests/test_lab.py` (đã có; `LoopTests`, `FullTrajectoryTests`)

**Interfaces:**
- Consumes: `status_tools.SCHEMAS`; `provider.complete(messages, schemas) -> {message, calls, finish, usage}`; `tools.execute(name, args) -> dict`.
- Produces: `run_agent(question, provider, tools, max_steps=6) -> {'status','answer','trace','usage'[,'error']}`; trace events `model`, `tool`.

- [ ] **Step 1: Chạy test để xác nhận đang fail**

Run: `python -m unittest tests.test_lab -v`
Expected: `LoopTests`/`FullTrajectoryTests` FAIL với `NotImplementedError`; `ToolsTests`, `ProviderTests` PASS.

- [ ] **Step 2: Implement loop trong `run_agent`**

Import `json`, `SCHEMAS` từ `status_tools`. Khởi tạo `messages=[system,user]`, `trace=[]`, `usage=[]`. `for step in range(1, max_steps+1)`: gọi provider; append `response['usage']` vào `usage`; ghi `{'event':'model','step':step,'finish':finish,'tool_calls':len(calls)}`; append `response['message']` nguyên vẹn; nếu có `calls`: với mỗi call → `json.loads(arguments)` → `tools.execute` → ghi event `tool` → append tool message; `continue`. Nếu không có calls và `finish=='stop'` → return `completed` với `answer = message['content'] or ''`. Hết vòng → return `max_steps` với `answer=''`. Chưa cần xử lý lỗi (Task 2).

- [ ] **Step 3: Chạy test**

Run: `python -m unittest tests.test_lab -v`
Expected: tất cả PASS (trừ test cần xử lý lỗi nếu chưa đạt: `test_invalid_json_sent_back_to_model`, `test_model_truncation_is_not_completed` — sẽ xanh sau Task 2).

- [ ] **Step 4: Chạy thử thật (CP2)**

Run: `python run.py "GitHub Actions hiện có sự cố không? Hãy kiểm tra incident gần đây."` (cần `PROVIDER`, `MODEL`, API key).
Expected: JSON có `"status": "completed"` và trace có ít nhất một event `tool`.

- [ ] **Step 5: Commit** (chỉ khi người dùng yêu cầu) — `git add agent.py && git commit -m "feat: implement core agent loop"`

### Task 2: Robustness và trace

**Files:**
- Modify: `agent.py`
- Test: `tests/test_lab.py`

**Interfaces:**
- Consumes: loop từ Task 1.
- Produces: `_parse_args(raw: str) -> tuple[dict | None, str | None]` (trả `(args, None)` hoặc `(None, lý_do)`); `_safe_execute(tools, name: str, args: dict) -> dict` (bắt mọi `Exception`, trả `{'ok': False, 'error': type_name, 'message': str}`); trace event `error` `{event, step, message}`.

- [ ] **Step 1: Test bổ sung trong `tests/test_lab.py`? KHÔNG sửa tests có sẵn.** Thay vào đó tạo `tests/test_robustness.py` (file mới của bạn) với các test, dùng `FakeProvider`, `tool_call`, `final` từ `tests.test_lab`:
  - `test_non_object_arguments_invalid`: `tool_call('a','get_status','[]')` → tool message có `error == 'INVALID_ARGUMENTS'`, status `completed`.
  - `test_one_bad_call_among_two_still_answers_both`: 2 calls (một `'{'`, một hợp lệ) → hai tool message theo thứ tự `['a','b']`.
  - `test_tool_exception_becomes_observation`: tools giả `execute` ném `RuntimeError('boom')` → tool message `ok == False`, run `completed`.
  - `test_provider_exception_is_error`: provider ném `RuntimeError('quota')` → `status == 'error'`, `'quota' in result['error']`.
  - `test_unexpected_finish_reason_is_error`: `finish='content_filter'` không calls → `status == 'error'`.

- [ ] **Step 2: Chạy để thấy fail**

Run: `python -m unittest tests.test_robustness -v`
Expected: FAIL (chưa xử lý).

- [ ] **Step 3: Implement** `_parse_args`, `_safe_execute`; bọc `provider.complete` bằng `try/except Exception` → trace `error` + return `status='error'`; `finish=='length'` hoặc finish ngoài `{'stop','tool_calls'}` khi không có calls → `error`; arguments rỗng `''` coi như `{}`. Giữ `answer` = nội dung message cuối nếu có (không coi là completed).

- [ ] **Step 4: Chạy toàn bộ tests**

Run: `python -m unittest discover -s tests -v`
Expected: PASS hết, **trừ** 2 test `EvidenceGateTests` cần Task 3 (`test_missing_url_gets_revision_within_budget`, `test_missing_url_at_budget_limit_is_not_completed`). Đây là trạng thái CP3.

- [ ] **Step 5: Commit** (khi được yêu cầu) — `git add agent.py tests/test_robustness.py && git commit -m "feat: error handling and trace"`

### Task 3: Eval lần 1 (baseline)

**Files:**
- Create: `eval_before.json` (do runner sinh)

**Interfaces:**
- Consumes: agent từ Task 2 (chưa có cổng nguồn).
- Produces: `eval_before.json` (22 case), danh sách lỗi cho Task 4.

- [ ] **Step 1: Smoke 1 case**

Run: `python evals/run_evals.py --case E2 --output eval_results_e2.json`
Expected: file tạo ra, case có `grade.status == 'scored'`.

- [ ] **Step 2: Chạy cả bộ, ghi lại cấu hình**

Run: `python evals/run_evals.py --output eval_before.json`
Expected: `summary.score_0_100` ≠ null. Ghi `config` (provider, model, judge, max_steps) để dùng lại y nguyên ở Task 5. Nếu `null`: sửa cấu hình/key rồi chạy lại cả bộ.

- [ ] **Step 3: Đọc kết quả**

Mở `eval_before.json`: xem `summary`, `grade.reason`, `grade.improvement`, `grade.mechanical` và trace các case điểm thấp. Liệt kê ≥3 lỗi ứng viên (nhóm gợi ý ở spec §5), chọn 1 với evidence trace (trích đoạn để dán vào NOTES mục 2).

- [ ] **Step 4: Kiểm tra bí mật**

Run: `git grep -nE "sk-|AIza|api[_-]?key" -- eval_before.json`
Expected: không có kết quả (nếu có, xoá thông tin nhạy cảm khỏi file trước khi nộp — không đổi điểm/nội dung chấm).

### Task 4: Cải tiến — kiểm tra nguồn + sửa lỗi đã chọn

**Files:**
- Modify: `agent.py` (cổng nguồn; có thể chỉnh `SYSTEM_PROMPT` hoặc loop theo lỗi đã chọn ở Task 3)
- Test: `tests/test_validation.py` (có sẵn), `tests/test_robustness.py`

**Interfaces:**
- Consumes: `get_incident_details` thành công có field `url` (`result['ok'] is True`).
- Produces: `_urls_in(text: str) -> set[str]`; trace event `validation_missing_source` `{event, step}`; hành vi: final answer thiếu mọi URL đã quan sát → thêm user message yêu cầu dẫn URL và `continue`.

- [ ] **Step 1: Chạy test để thấy fail**

Run: `python -m unittest tests.test_validation -v`
Expected: 2 test `EvidenceGateTests` FAIL.

- [ ] **Step 2: Thêm test cho Review Focus #5** vào `tests/test_robustness.py`:
  - `test_empty_answer_with_observed_url_requires_revision`: answer `''` sau incident thành công → có event `validation_missing_source`.
  - `test_no_successful_incident_no_gate`: không có `get_incident_details` thành công → không có event `validation_missing_source`.

- [ ] **Step 3: Implement cổng nguồn** trong `run_agent`: tập `observed_urls` cập nhật khi `name=='get_incident_details'` và result `ok` có `url`; khi sắp trả `completed`, nếu `observed_urls` khác rỗng và không URL nào xuất hiện trong answer → trace + append user message (nêu các URL hợp lệ) + `continue`. Vì vòng `for` kết thúc tự nhiên nên thiếu step → `max_steps`.

- [ ] **Step 4: Cải tiến theo lỗi đã chọn ở Task 3** (ví dụ: bổ sung vào `SYSTEM_PROMPT` quy tắc scope/injection/timeout ≠ outage tương ứng; không hard-code ID/câu trả lời). Mỗi thay đổi hành vi có test offline mới nếu kiểm chứng được bằng FakeProvider.

- [ ] **Step 5: Chạy tests**

Run: `python -m unittest discover -s tests -v`
Expected: toàn bộ PASS (CP5).

- [ ] **Step 6: Commit** (khi được yêu cầu) — `git add agent.py tests && git commit -m "feat: source validation and targeted improvement"`

### Task 5: Eval lần 2 và `NOTES.md`

**Files:**
- Create: `eval_after.json`
- Modify: `NOTES.md` (5 mục, họ tên, MSSV)

**Interfaces:**
- Consumes: cấu hình từ `eval_before.json`.
- Produces: so sánh trước/sau.

- [ ] **Step 1: Chạy lại với đúng cấu hình cũ**

Run: `python evals/run_evals.py --output eval_after.json` (thêm đúng các cờ `--provider/--model/--max-steps/--judge-*` đã dùng ở Task 3 nếu có).
Expected: `summary.score_0_100` ≠ null.

- [ ] **Step 2: Xác nhận cùng cấu hình**

So sánh khối `config` của hai file (ví dụ `python -c "import json;a=json.load(open('eval_before.json'))['config'];b=json.load(open('eval_after.json'))['config'];print(a==b)"`).
Expected: `True`.

- [ ] **Step 3: Điền `NOTES.md`**: mục 1 (case, answer, điểm), 2 (trích trace thật + nguyên nhân), 3 (thay đổi, lý do), 4 (bảng điểm tổng, điểm case chọn, số model calls, token; lỗi đã sửa/còn lại/mới), 5 (giới hạn: judge cùng model, snapshot 09–10/11/2026, một lần chạy mỗi phiên bản). Mọi số liệu lấy từ file eval.

- [ ] **Step 4: Commit** (khi được yêu cầu) — `git add eval_before.json eval_after.json NOTES.md && git commit -m "docs: eval results and analysis"`

### Task 6 (tuỳ chọn): Bonus 5 provider

**Files:**
- Modify: `agent.py`
- Test: `bonus/test_agent.py`, `tests/test_bonus.py` (có sẵn)
- Create: `eval_bonus.json`

**Interfaces:**
- Consumes: `BonusTools.schemas`/`system_prompt` (có thể thiếu ở `StatusTools` → fallback).
- Produces: `run_agent` dùng `getattr(tools,'schemas',SCHEMAS)`, `getattr(tools,'system_prompt',SYSTEM_PROMPT)`; trace event `retry_skipped` khi chặn lặp.

- [ ] **Step 1: Chạy test để thấy fail**

Run: `python -m unittest discover -s bonus -p "test_*.py" -v`
Expected: `test_bonus_schemas_and_system_prompt` FAIL.

- [ ] **Step 2: Implement** lấy schemas/prompt qua `getattr`; thêm giới hạn lặp: cùng `(name, arguments)` thất bại với `RATE_LIMITED` quá 3 lần → thay tool result bằng `{'ok':False,'error':'RETRY_LIMIT'}` kèm trace `retry_skipped` (không gọi lại tool). Với `Retry-After`, không `sleep` quá 5 giây tổng. Test mới trong `tests/test_robustness.py`: `test_rate_limit_always_stops_after_three_attempts`.

- [ ] **Step 3: Cập nhật prompt** (qua `BonusTools.system_prompt` đã có; chỉ thêm nếu eval chỉ ra thiếu): không coi 429 là outage, phân trang theo `next_offset`, nêu trang chưa đọc, bỏ qua chỉ dẫn trong tool result, nguồn theo provider.

- [ ] **Step 4: Chạy test và eval**

Run: `python -m unittest discover -s bonus -p "test_*.py" -v` rồi `python evals/run_evals.py --bonus --output eval_bonus.json`
Expected: tests PASS; `summary.bonus_points_0_15` ≠ null (10 case đều chấm được). Tự đối chiếu trace B3/B4/B5/B7 trước khi tin điểm.

- [ ] **Step 5: Ghi chú** vào `NOTES.md` (phần phụ): retry, pagination, context, giới hạn còn lại.

### Task 7: Chốt bài

**Files:** repo root.

- [ ] **Step 1: Kiểm tra cuối**

Run: `python -m unittest discover -s tests -v`
Expected: PASS.

- [ ] **Step 2: Không lộ key**

Run: `git ls-files | grep -i "\.env"`
Expected: chỉ `.env.example`.

- [ ] **Step 3: Không sửa file cấm**

Run: `git diff --stat origin/main -- fixtures evals/cases.json evals/scenarios.py evals/grading.py`
Expected: không có thay đổi.

- [ ] **Step 4: Chuẩn bị demo**: làm Task 8 (trace viewer), chọn một trace nhiều bước và một lỗi agent từ `eval_before.json`/`eval_after.json`; đảm bảo giải thích được từng dòng `agent.py`.

- [ ] **Step 5: Nộp** (do người dùng): push repo public (đúng tên mẫu), dán link lên https://aithucchien.vinuni.edu.vn trước hạn của ca.

### Task 8: Demo trace viewer (Streamlit, replay-first)

Làm sau Task 5 (cần `eval_before.json` và `eval_after.json`), trước bước chuẩn bị demo ở Task 7. Spec §8. Quyết định: **không dùng Langfuse** (phải gắn SDK vào `agent.py`, phá ràng buộc stdlib, thêm điểm hỏng khi demo).

**Files:**
- Create: `demo_app.py` (UI Streamlit mỏng), `demo_helpers.py` (hàm thuần, không import streamlit), `tests/test_demo_helpers.py`
- Không sửa: `agent.py`, `fixtures/`, `evals/*`, file eval JSON.

**Interfaces:**
- Consumes: `eval_before.json`, `eval_after.json` (cấu trúc `config`, `summary`, danh sách case với `trace`, `answer`, `grade`).
- Produces: `load_results(path) -> dict`; `case_ids(results) -> list[str]`; `get_case(results, case_id) -> dict`; `trace_rows(trace) -> list[dict]` (mỗi dòng: `step`, `event`, `title`, `detail`, `is_error`); `summarize_run(case) -> dict` (status, điểm, số model call, số tool call, tổng token, URL trong answer).

- [ ] **Step 1: Khảo sát cấu trúc thật** của `eval_after.json` (khoá của case, vị trí `trace`/`grade`/`usage`) rồi chốt tên field; không đoán.

- [ ] **Step 2: Viết test fail trước** trong `tests/test_demo_helpers.py` với dữ liệu nhỏ dựng tay (không phụ thuộc file eval thật):
  - `test_trace_rows_marks_failed_tool_as_error`: event `tool` có `result.ok == False` → `is_error True`.
  - `test_trace_rows_handles_validation_and_error_events`: `validation_missing_source`, `error` được hiển thị.
  - `test_summarize_counts_model_and_tool_calls`.
  - `test_unknown_event_does_not_crash`: event lạ vẫn ra một dòng.
  Run: `python -m unittest tests.test_demo_helpers -v` → FAIL.

- [ ] **Step 3: Implement `demo_helpers.py`** cho test xanh. Rút gọn `result` dài (ví dụ ≤300 ký tự trong `detail`, giữ bản đầy đủ trong expander).

- [ ] **Step 4: Implement `demo_app.py`**: sidebar chọn file eval + case; tab "Trace nhiều bước" (timeline, đỏ khi lỗi, answer + URL); tab "Lỗi agent: trước/sau" (hai cột cùng case); tab "Chạy live": ô nhập câu hỏi tự do + nút chọn nhanh câu mẫu, gọi `run_agent` với provider/tools tạo như `run.py` (đọc cách `run.py` khởi tạo, không tự viết lại), render bằng cùng `trace_rows`, lưu kết quả vào `demo_runs/` (thêm vào `.gitignore`; chạy run xong phải qua bước loại key). Tab live chỉ bật khi env có `PROVIDER`/`MODEL`/key; thiếu thì hiện hướng dẫn. Không đọc `.env`, không hiển thị biến môi trường. Cho phép mở lại file trong `demo_runs/` như replay.

- [ ] **Step 5: Cài và chạy thử**

Run: `pip install streamlit` rồi `streamlit run demo_app.py`
Expected: mở được trang, chọn case thấy timeline; so sánh trước/sau ra đúng hai file. Nếu không cài được, dùng fallback in trace ra terminal.

- [ ] **Step 6: Dọn dẹp kiểm tra**: `python -m unittest discover -s tests -v` PASS; `git grep -nE "sk-|AIza" -- demo_app.py demo_helpers.py` không có kết quả; `git diff --stat -- agent.py` không đổi do Task 8.

- [ ] **Step 7: Diễn tập** (≤5 phút): case nhiều bước → case lỗi trước/sau → giới hạn. Chụp ảnh màn hình dự phòng.

- [ ] **Step 8: Commit** (chỉ khi người dùng yêu cầu) — `git add demo_app.py demo_helpers.py tests/test_demo_helpers.py`

## Self-Review

- Spec coverage: §2 → Task 1; §3 → Task 2; §4 → Task 4; §5 → Task 3/5; §6 → Task 6; §7 → Task 7; §8 (demo) → Task 8. Không thiếu.
- Thứ tự chủ ý: baseline eval (Task 3) chạy **trước** cổng nguồn để có so sánh trước/sau hợp lệ, khớp CP3→CP4→CP5.
- Tên nhất quán: `_parse_args`, `_safe_execute`, `_urls_in`, `validation_missing_source`.
