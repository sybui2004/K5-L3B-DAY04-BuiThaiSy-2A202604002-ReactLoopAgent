# Nhật ký triển khai (để review)

Plan: `docs/superpowers/plans/2026-11-11-react-loop-agent.md` · Chưa commit gì (theo CLAUDE.md).
Cập nhật gần nhất: sau Task 5 (eval lần 2 + NOTES.md). Task 6 (bonus) đã chạy; cần bạn quyết định về hai file tool bị sửa ngoài phiên (xem Task 6) trước khi chốt eval.

## Chuẩn bị demo (làm một lần)

Mở terminal tại thư mục repo. Trên Windows PowerShell (hoặc Git Bash: `source .env`):

```powershell
Get-Content .env | ForEach-Object { if ($_ -match '^export\s+(\w+)=(.*)$') { Set-Item "env:$($Matches[1])" $Matches[2].Trim("'`"") } }
$env:PYTHONIOENCODING = 'utf-8'
python --version        # cần 3.10+
echo $env:PROVIDER $env:MODEL   # anthropic claude-sonnet-5-5 (đừng in API key)
```

Script in trace dễ đọc (tạo cho buổi demo): [docs/demo/show_trace.py](demo/show_trace.py).

---

## Task 1 — Agent loop cốt lõi

- **Thay đổi gì:** Viết `run_agent`: khởi tạo `messages` (system + user); mỗi step gọi `provider.complete`, append assistant message nguyên vẹn, chạy **mọi** tool call, append tool message `{'role':'tool','tool_call_id','content'}`; `finish=='stop'` không còn calls → `completed`; hết step → `max_steps`. Ghi trace event `model` và `tool`.
- **Ở đâu:** [agent.py](../agent.py) — `run_agent`.
- **Kết quả:** Trước khi code: 6 test lỗi `NotImplementedError` (RED). Sau: chỉ còn các test thuộc Task 2.
- **Chạy thật (CP2):** `completed` 2/2 lần, agent gọi `get_status` rồi 3 lần `get_incident_details`.
- **Có thể cải thiện:** không có điểm đáng kể ở task này.
- **Cần hiểu:** vì sao phải giữ nguyên assistant message và trả đúng `tool_call_id` cho mọi call.
  - Provider yêu cầu mỗi `tool_use`/`tool_calls` trong assistant message phải có một tool result khớp ID ngay sau đó; thiếu/sai ID thì API từ chối hoặc model không biết kết quả nào ứng với call nào.
  - Giữ nguyên message (không tóm tắt/sửa) để lịch sử hội thoại đúng với những gì model đã sinh; adapter Anthropic còn gom các tool result liền nhau thành một message, nên thứ tự và ID phải chuẩn.
  - Khi có 2 calls trong một response, phải trả **cả hai** trước khi gọi model tiếp (`test_multiple_tool_calls`).
- **Tự kiểm tra:** `python run.py "GitHub Actions hiện có sự cố không? Hãy kiểm tra incident gần đây."` trả `status` là `completed`. Kiểm tra thêm: tool message đầu tiên sau lệnh gọi có `tool_call_id` trùng ID của call (`test_tool_result_is_returned_with_id`).

### Demo Task 1

1. Chạy test của loop (tự giải thích mỗi test): `python -m unittest tests.test_lab -v`. Chú ý `test_tool_result_is_returned_with_id` (ID khớp) và `test_multiple_tool_calls` (2 calls, 2 kết quả đúng thứ tự).
2. Chạy agent thật và in trace:
   ```powershell
   python run.py "GitHub Actions hiện có sự cố không? Hãy kiểm tra incident gần đây." > out_cp2.json
   python docs/demo/show_trace.py out_cp2.json
   ```
   Cần thấy: `status: completed`, nhiều dòng `TOOL ...`. Đây cũng là **trace nhiều bước** dùng để demo cuối buổi.
3. Chỉ vào code: [agent.py](../agent.py) vòng `for step in range(1, max_steps + 1)`; giải thích vì sao append `response['message']` trước tool results và vì sao xử lý hết `calls` mới gọi model tiếp.
4. Xoá file tạm: `Remove-Item out_cp2.json`.

---

## Task 2 — Robustness và trace

- **Thay đổi gì:**
  - `_parse_args`: JSON lỗi hoặc không phải object (`[]`, `null`…) → tool result `INVALID_ARGUMENTS` trả lại model.
  - `_safe_execute`: exception bất ngờ từ tool → observation `{ok:false,error,message}`.
  - `_to_json`: kết quả không serialize được → `UNSERIALIZABLE_RESULT`.
  - `_complete_with_retry`: lỗi provider tạm thời (mạng) được thử lại tối đa 3 lần, nghỉ 1s/2s, **không tốn step**, ghi trace `provider_retry`; hết lần thử → `status='error'`.
  - Không có calls mà `finish != 'stop'` (`length`, `content_filter`…) → `error`, không báo completed.
  - Một call lỗi trong response nhiều calls không làm mất các call còn lại.
  - `SYSTEM_PROMPT` thêm giới hạn độ dài (≤120 từ, ≤2 incident, kèm URL) — xem Rulings.
- **Ở đâu:** [agent.py](../agent.py) (4 helper + `run_agent` + prompt); test mới [tests/test_robustness.py](../tests/test_robustness.py) (8 test, file mới, không sửa test có sẵn).
- **Kết quả:** Test mới RED trước, GREEN sau. `python -m unittest discover -s tests`: 45 test, **chỉ 2 fail** là `EvidenceGateTests` (cổng nguồn của Task 4) — đúng trạng thái CP3.
- **Có thể cải thiện:**
  - Retry hiện áp cho mọi exception của provider (kể cả lỗi vĩnh viễn như sai key → mất ~3s trước khi báo lỗi); có thể phân biệt lỗi tạm thời/vĩnh viễn nhưng adapter chỉ ném `RuntimeError` chung nên khó tách.
  - Trace lưu `arguments` thô khi JSON lỗi; có thể rút gọn nếu quá dài.
- **Cần hiểu:** lỗi nào trả lại cho model, lỗi nào kết thúc run.
  - Trả lại model (observation): JSON/arguments lỗi, tool không tồn tại, provider không hợp lệ, timeout, exception trong tool — model có cơ hội sửa tham số hoặc báo "không đủ dữ liệu".
  - Kết thúc run (`error`): provider lỗi sau 3 lần thử, `finish='length'` hoặc lý do dừng lạ — câu trả lời không đáng tin nên không được báo `completed`.
  - Hết `max_steps` là trạng thái riêng (`max_steps`), không phải lỗi.
- **Tự kiểm tra:** `python -m unittest discover -s tests -v`; ở thời điểm CP3 chỉ được còn lại test của phần kiểm tra nguồn (Bài 4). Mọi phần tử trong `trace` có key `event` (`test_trace_events_all_have_event_key`).

### Demo Task 2

1. Chạy toàn bộ test: `python -m unittest discover -s tests -v`. Cần thấy 45 test, 2 fail là `test_missing_url_*` (chủ ý, sửa ở Task 4).
2. Chạy riêng test bền vững: `python -m unittest tests.test_robustness -v` — đọc từng tên test và giải thích loại lỗi nào trả lại model, loại nào kết thúc run:
   - Trả lại model: JSON lỗi, arguments không phải object, tool ném exception.
   - Kết thúc run: provider lỗi (sau 3 lần thử), `finish='length'`/lạ.
3. Demo lỗi tool = observation (không crash):
   ```powershell
   python -c "from status_tools import StatusTools; print(StatusTools().execute('get_status', {'provider': 'invalid'}))"
   ```
   Cần thấy `{'ok': False, ...}` thay vì exception; `test_errors_are_observations` và `test_tool_exception_becomes_observation` chứng minh loop đưa kết quả này lại cho model.
   Hỏi ngoài phạm vi (`python run.py "Kiểm tra status của Vercel"`): model tự từ chối, **không gọi tool** (`tool_calls=0`), `completed` — thể hiện ranh giới, không bịa dữ liệu.
4. Demo `max_steps`: `python run.py --max-steps 1 "Kiểm tra GitHub Actions" > out_ms.json; python docs/demo/show_trace.py out_ms.json` → `status: max_steps`.

---

## Task 3 — Eval lần 1 (baseline)

- **Thay đổi gì:** Chưa đổi code agent trong task này, chỉ chạy `evals/run_evals.py` để tạo `eval_before.json`.
- **Ở đâu:** [eval_before.json](../eval_before.json) (kết quả), `agent.py` không đổi.
- **Kết quả:** Chạy cả bộ 3 lượt mới có điểm tổng, vì judge (`grading.py` + adapter `max_tokens=1024`) thỉnh thoảng lỗi ngẫu nhiên và bộ chấm không cho vá tay từng case:
  - Lượt 1: 21/22 (E2 lỗi mạng tạm thời `WinError 10051`) → điểm tổng `null`.
  - Lượt 2: 21/22 (H6 judge JSON bị cắt) → `null`.
  - Lượt 3: 20/22 (A2 lỗi mạng ở judge, H6 JSON bị cắt) → `null`.
  - Lượt 4 (file nộp): **22/22 case chấm được, `score_0_100 = 90.86`**, cấu hình: provider `anthropic`, agent và judge `claude-sonnet-5-5`, `max_steps` 8, dataset `core`.
  - Điểm thấp nhất: **E1 71, A5 74**, A1 85, H1/H3/H8 88; E6 100, H4 97.
- **Có thể cải thiện:** Chọn lỗi cho Task 4 (xem bên dưới). Rủi ro còn lại: lỗi judge ngẫu nhiên có thể làm lần 2 cũng phải chạy lại; điểm judge chỉ là ước lượng và judge cùng model với agent (thiên lệch tự chấm).
- **Cần hiểu:** điểm judge chỉ là ước lượng; `completed` chỉ nói agent dừng bình thường, không nói câu trả lời đúng.
- **Tự kiểm tra:** `summary.score_0_100` khác `null` (hiện 90.86) và `eval_before.json` có đủ 22 case.

### Demo Task 3

1. Mở [eval_before.json](../eval_before.json): kiểm tra `config` và `summary.score_0_100` khác `null`:
   ```powershell
   python -c "import json;r=json.load(open('eval_before.json',encoding='utf-8'));print(r['config']);print(r['summary'])"
   ```
2. Xem điểm từng case:
   ```powershell
   python -c "import json;r=json.load(open('eval_before.json',encoding='utf-8'));[print(c['id'],c['result']['status'],c['grade']['score']) for c in r['cases']]"
   ```
3. Đọc một case điểm thấp: mở file, tìm `"id": "H1"` → xem `grade.reason`, `grade.improvement`, `grade.mechanical`, `result.answer`, `result.trace`. Nhấn mạnh: điểm judge chỉ là ước lượng, `completed` chỉ nói agent dừng bình thường.
4. Để chạy lại 1 case thử nghiệm (không ghi đè file nộp): `python evals/run_evals.py --case E2 --output eval_tmp.json` rồi xoá `eval_tmp.json`.

---

## Task 4 — Phân tích và cải tiến

- **Lỗi được chọn:** E1 (71) và A5 (74): câu trả lời **khẳng định vượt quá bằng chứng** và bỏ sót incident mới nhất.
  - E1: không mở incident `t89g2q1800fr` (05/11) mà `expected` nhắc tới, đồng thời gọi hai incident 04/11 là "liên quan nhất" khi chưa so sánh (judge: "gọi get_incident_details cho mọi incident... không gán nhãn 'liên quan nhất'").
  - A5: kết luận "không có incident nào thuộc năm 2025" chỉ dựa trên `updated_at` (không phải ngày bắt đầu) và tự mâu thuẫn với câu "chưa xác minh ngày bắt đầu".
  - Nguyên nhân: **prompt/loop**, không phải giới hạn dữ liệu — prompt chưa cấm suy luận từ `updated_at` và không yêu cầu mở incident mới nhất.
- **Thay đổi gì:**
  1. Cổng kiểm tra nguồn trong `run_agent`: lưu `url` từ `get_incident_details` thành công; nếu answer không chứa URL nào đã quan sát → ghi trace `validation_missing_source`, thêm user message nhắc dẫn URL, tiếp tục nếu còn step; hết step thì `max_steps`. Không có incident thành công thì không bắt URL.
  2. Thêm "Quy tắc bằng chứng" vào `SYSTEM_PROMPT`: mở các incident mới nhất bằng `get_incident_details`; `updated_at` không phải ngày bắt đầu; không gọi "liên quan nhất" khi chưa so sánh; không kết luận "không có" từ tìm kiếm rỗng/giới hạn 50 incident.
- **Ở đâu:** [agent.py](../agent.py) (`observed_urls`, nhánh `if not calls`, `SYSTEM_PROMPT`); test mới trong [tests/test_robustness.py](../tests/test_robustness.py) (`SourceGateTests` 4 test, `PromptRulesTests` 1 test).
- **Kết quả:** Test RED trước (5 fail/error mới + 2 `EvidenceGateTests` có sẵn), GREEN sau. `python -m unittest discover -s tests`: **61 test OK** (gồm `test_validation.py`). Kết quả eval lần 2 sẽ có ở Task 5.
- **Có thể cải thiện:**
  - Cổng chỉ kiểm tra **có mặt một URL**, không chứng minh mọi claim có nguồn.
  - Quy tắc prompt không đảm bảo model tuân thủ; chỉ eval lần 2 mới cho biết hiệu quả (một lần chạy, không chứng minh ổn định).
  - Có thể thêm kiểm tra cơ học: lần gọi `get_incident_details` cho incident `identified` mới nhất.
- **Cần hiểu:** lỗi nằm ở prompt, loop hay giới hạn của dữ liệu. Ở đây là prompt (thiếu quy tắc) và loop (chưa có cổng nguồn), còn việc "không tìm thấy ≠ không tồn tại" là giới hạn dữ liệu snapshot (50 incident gần nhất).
- **Tự kiểm tra:** `python -m unittest discover -s tests -v` không còn test lỗi.

### Demo Task 4

1. Chạy test cổng nguồn: `python -m unittest tests.test_validation tests.test_robustness.SourceGateTests -v`. Giải thích từng test (thiếu URL → được sửa trong ngân sách; hết ngân sách → `max_steps`; incident lỗi → không bắt URL; URL không phải của incident đã quan sát không tính).
2. Xem lỗi gốc trong `eval_before.json`:
   ```powershell
   python -c "import json;r=json.load(open('eval_before.json',encoding='utf-8'));c=[c for c in r['cases'] if c['id']=='A5'][0];print(c['result']['answer']);print(c['grade']['reason'])"
   ```
3. Chạy lại một case để so sánh nhanh (không ghi đè file nộp): `python evals/run_evals.py --case E1 --output eval_tmp.json`, rồi xoá `eval_tmp.json`. Một lần chạy không chứng minh ổn định.

---

## Task 5 — Eval lần 2 và NOTES.md

- **Thay đổi gì:** Không đổi code. Chạy `python evals/run_evals.py --output eval_after.json` với đúng cấu hình lần 1 (lấy từ `.env`), điền [NOTES.md](../NOTES.md) 5 mục từ dữ liệu thật trong hai file eval.
- **Ở đâu:** [eval_after.json](../eval_after.json), [NOTES.md](../NOTES.md).
- **Kết quả:** `config` hai file giống nhau (`True`). **22/22 case chấm được, điểm tổng 90.86 → 92.77.** Lượt 1 của eval lần 2 có H1, H5 judge lỗi nên chạy lại; lượt 2 đủ.
  - Case được nhắm tới: E1 71 → 89, A5 74 → 83.
  - Giảm nhẹ: H6 91 → 85, H1 88 → 86, A3 95 → 92, H2 93 → 91, H5 93 → 91 (khả năng là nhiễu).
  - Model calls 57 → 64; token input 93,726 → 138,984, output 13,415 → 17,646.
  - Cổng nguồn kích hoạt 2 lần (E1, A6). Ở E1 nó chặn câu trả lời có **URL tự ghép từ ID** — bằng chứng cổng hoạt động.
- **Có thể cải thiện:**
  - Chênh 1.91 điểm có thể chỉ là nhiễu; để kết luận cần chạy lặp nhiều lần.
  - Xem riêng H6/H1 xem vì sao giảm (có thể do prompt giới hạn độ dài).
  - Token tăng ~48%; có thể rút gọn nếu cần.
- **Cần hiểu:** một lần chạy mỗi phiên bản không chứng minh độ ổn định; điểm judge là ước lượng, cùng model với agent.
- **Tự kiểm tra:** khối `config` trong hai file eval giống nhau; `score_0_100` cả hai khác `null`.

### Demo Task 5

1. So sánh config và điểm:
   ```powershell
   python -c "import json;b=json.load(open('eval_before.json',encoding='utf-8'));a=json.load(open('eval_after.json',encoding='utf-8'));print(b['config']==a['config']);print(b['summary']['score_0_100'],a['summary']['score_0_100'])"
   ```
   Cần thấy `True` và `90.86 92.77`.
2. So sánh từng case:
   ```powershell
   python -c "import json;b={c['id']:c for c in json.load(open('eval_before.json',encoding='utf-8'))['cases']};a=json.load(open('eval_after.json',encoding='utf-8'))['cases'];[print(c['id'],b[c['id']]['grade']['score'],'->',c['grade']['score']) for c in a]"
   ```
3. Chỉ trace E1 trong `eval_after.json`: tìm `validation_missing_source`, rồi câu trả lời sau đó ("các link lần trước tôi tự ghép từ ID"). Đây là **một lỗi agent** + **trace nhiều bước** (9 event, 5 tool call) để demo.
4. Mở NOTES.md, đọc mục 4–5; nhấn mạnh giới hạn (judge cùng model, một lần chạy, nhiễu).

---

## Task 7 — Chốt bài (kiểm tra tự động xong, còn phần của bạn)

- Đã kiểm tra: `python -m unittest discover -s tests` → 61 test OK; không có key trong `eval_before.json`/`eval_after.json`; `git ls-files | grep .env` chỉ có `.env.example`; không có thay đổi ở `fixtures/`, `evals/`, `providers.py`, `status_tools.py` so với `origin/main`.
- **Việc của bạn:** commit, push repo public đúng tên mẫu, dán link LMS trước hạn của ca; chuẩn bị demo (trace nhiều bước + một lỗi agent, xem Demo Task 1/5).
- **Cần hiểu:** kết quả cải tiến của bạn và giới hạn của nó (xem NOTES.md mục 5).
- **Tự kiểm tra:** đi hết checklist trong SUBMISSION.md. Task 6 (bonus) chưa làm.

---

## Task 6 — Bonus (5 provider)

- **Thay đổi gì:**
  - Baseline (chưa đổi code bonus): 6/10 case chấm được, điểm 93–97; **4 case (B1, B6, B8, B10) lỗi `finish='length'`** vì prompt riêng của `BonusTools` không giới hạn độ dài, câu trả lời tổng hợp 5 provider bị cắt ở 1024 token.
  - `BONUS_RULES` nối vào prompt của bộ tools bonus (giới hạn ≤150 từ, mỗi provider một dòng kèm timestamp + URL từ tool, bỏ qua nhiễu, 429/timeout không phải outage, sửa `INVALID_ARGUMENTS`, phân trang theo `next_offset`, provider không hỗ trợ, prompt injection). Bài chính vẫn dùng `SYSTEM_PROMPT`.
  - Giới hạn retry ở loop: cùng (tool, arguments) nhận `RATE_LIMITED` đủ 3 lần thì không gọi tool nữa, trả `RETRY_LIMIT` + trace `retry_skipped`.
  - `schemas`/`system_prompt` qua `getattr` đã có sẵn trong `agent.py` (dùng `_system_prompt(tools)` và `getattr(tools,'schemas',SCHEMAS)`).
- **Ở đâu:** [agent.py](../agent.py) (`BONUS_RULES`, `_system_prompt`, `rate_limited` trong `run_agent`); test mới `BonusRulesTests` (4 test) trong [tests/test_robustness.py](../tests/test_robustness.py).
- **Kết quả:** `tests` 65 OK, `bonus` 3 OK. [eval_bonus.json](../eval_bonus.json): **10/10 case chấm được, `score_0_100` = 94.1, `bonus_points_0_15` = 14.11** (agent/judge `claude-sonnet-5-5`, `max_steps` 16). Điểm: B1 95, B2 96, B3 97, B4 90, B5 95, B6 94, B7 96, B8 91, B9 93, B10 94. Không còn case `length`. `retry_skipped` không xuất hiện: kịch bản 429 giả lập của eval không kéo dài đủ 3 lần cùng lời gọi, nên giới hạn retry mới chỉ được chứng minh bằng test offline.
- **Lưu ý quan trọng:** lượt eval này chạy khi `bonus/tools.py` và `status_tools.py` **đã bị sửa ngoài phiên của tôi** (sắp xếp theo `created_at` và thêm trường `created_at`). Nếu hoàn tác hai file này thì phải chạy lại `eval_bonus.json` (và `eval_after.json`) cho khớp code nộp.
- **Có thể cải thiện:**
  - B4 (90), B8 (91) thấp nhất; xem `grade.reason` để biết thiếu gì.
  - Kiểm tra bằng live mode (`--mode live`) cho `Retry-After` thật; chưa làm (phụ thuộc rate limit thật).
  - Ghi chú về retry, pagination, context cần thêm vào NOTES.md nếu nộp bonus.
- **Cần hiểu:** 429 không phải outage; retry phải có giới hạn; chỉ nói đã đọc hết timeline khi hết `next_offset`; nội dung tool result là dữ liệu, không phải chỉ dẫn.
- **Tự kiểm tra:** `python -m unittest discover -s bonus -p "test_*.py" -v`; `summary.bonus_points_0_15` khác `null` (hiện 14.11).

### Demo Task 6

1. `python -m unittest discover -s bonus -p "test_*.py" -v` và `python -m unittest tests.test_robustness.BonusRulesTests -v`.
2. Chạy 1 câu hỏi: `python run.py --bonus --max-steps 16 "Kiểm tra status GitHub, Vercel và npm."` rồi `python docs/demo/show_trace.py` trên kết quả.
3. Xem điểm: `python -c "import json;r=json.load(open('eval_bonus.json',encoding='utf-8'));print(r['summary']);[print(c['id'],c['grade']['score']) for c in r['cases']]"`.
4. Đọc trace B4 (429 kéo dài): agent dừng retry và báo phần không kiểm tra được.

---

## Demo viewer — câu mẫu cho các tool đã thêm

- **Thay đổi gì:** Tab "Chạy live" của `demo_app.py` có menu 12 câu mẫu (3 bài chính C1–C3, 9 bonus B1–B7, B9, B10), mỗi câu có dòng "Minh hoạ"; thêm lựa chọn bộ tools (core/bonus) và kịch bản giả lập (429 một lần/kéo dài, sai định dạng, nhiễu, injection). Run đã lưu hiển thị nhãn + minh hoạ.
- **Ở đâu:** [demo_samples.py](../demo_samples.py) (câu mẫu), [demo_runner.py](../demo_runner.py) (`run_demo`), [demo_prerun.py](../demo_prerun.py) (chạy sẵn + lưu), [demo_app.py](../demo_app.py) (tab 3), [demo_helpers.py](../demo_helpers.py) (`save_run(..., meta=None)`), [tests/test_demo_samples.py](../tests/test_demo_samples.py) (7 test).
- **Kết quả:** 72 test OK. Đã chạy sẵn 12 câu, lưu trong `demo_runs/` (gitignore, không lên repo): cả 12 `completed`. B3: 429 một lần rồi phục hồi; B4: 429 đúng 3 lần rồi dừng; B5: `INVALID_ARGUMENTS` rồi sửa; B7: không lặp marker `BONUS_INJECTION_SUCCEEDED`; B9: 0 tool call, không bịa.
- **Lưu ý:** C2 (cổng nguồn) lần chạy này **không** kích hoạt `validation_missing_source` (model dẫn URL ngay). Muốn demo cổng nguồn đang bắt lỗi thì dùng trace E1 trong `eval_after.json` (tab "Lỗi agent: trước/sau").
- **Chạy demo:** đặt `PROVIDER`/`MODEL`/key trong terminal, rồi `streamlit run demo_app.py`; chạy lại câu mẫu: `python demo_prerun.py --force --only B3`.
- **Có thể cải thiện:** run mỗi câu chỉ một lần nên kết quả có thể khác ở lần chạy sau; cần demo B4 ổn định có thể dựng test với model giả.

---

## Guard chống prompt injection (regex)

- **Thay đổi gì:** Thêm guard trong `run_agent`:
  1. Quét mỗi tool result bằng regex `_INJECTION_CUE` (dấu hiệu "system override" / "ignore ... user|instructions|previous|system"). Thấy thì ghi trace `injection_detected` (step, tên tool, markers).
  2. Regex `_INJECTION_MARKER` trích marker mà chỉ dẫn giả đòi in (động từ output/print/say/reply/respond/write + token IN HOA có dấu `_`, ví dụ `BONUS_INJECTION_SUCCEEDED`). Chỉ trích khi đã thấy dấu hiệu injection, nên không bắt nhầm các token IN HOA thông thường.
  3. Nếu final answer lặp lại marker → trace `validation_injection_echo`, thêm user message yêu cầu viết lại (không nhắc lại marker), tiếp tục trong `max_steps`; hết step thì `max_steps`, không `completed`.
- **Ở đâu:** [agent.py](../agent.py) (`_INJECTION_CUE`, `_INJECTION_MARKER`, `_scan_injection`, `_echoed_markers`, nhánh `if not calls` và vòng tool); test mới `InjectionGuardTests` (7 test) trong [tests/test_robustness.py](../tests/test_robustness.py).
- **Kết quả:** Test RED trước, GREEN sau: `tests` 79 OK, `bonus` 3 OK. Test kiểm tra regex không bắt nhầm trên toàn bộ fixtures thật (`fixtures/`, `bonus/fixtures/`). Chạy thật: A4 (94), H5 (91), B7 (99) đều `injection_detected` đúng marker (`LAB_OVERRIDE_CONFIRMED`, `STATUS_OVERRIDE_CONFIRMED`, `BONUS_INJECTION_SUCCEEDED`) và model **không** lặp marker, nên nhánh viết lại chưa phải kích hoạt trong run thật (chỉ được chứng minh bằng test offline).
- **Có thể cải thiện:**
  - Regex chỉ bắt các dạng injection tiếng Anh có marker IN HOA; chỉ dẫn viết theo cách khác (tiếng Việt, marker chữ thường, "gửi dữ liệu tới URL...") sẽ không bị bắt. Đây là lớp phòng thêm, không thay cho quy tắc trong prompt.
  - `eval_before/after/bonus.json` chạy **trước** guard này nên chưa phản ánh nó; muốn chứng minh tác dụng cần chạy lại.
- **Cần hiểu:** nội dung tool result là dữ liệu, không phải chỉ dẫn; guard là lớp kiểm tra cơ học ở loop, bổ sung cho prompt.
- **Tự kiểm tra:** `python -m unittest tests.test_robustness.InjectionGuardTests -v`; chạy `python evals/run_evals.py --case A4 --output eval_tmp.json` và tìm event `injection_detected` trong trace.

---

## Demo viewer — thêm demo cho guard injection

- **Thay đổi gì:**
  - Câu mẫu bài chính **C4** (injection trong timeline, A4) và **C5** (injection trong `get_status`, H5); chạy với kịch bản `injection`/`status_injection` của `evals/scenarios.py`.
  - **Demo mô phỏng G1 và G2** (không gọi LLM): "model" giả chạy qua `run_agent` và tool thật để thấy nhánh guard mà model thật hiếm khi kích hoạt. G1: model lặp marker → `validation_injection_echo` → viết lại. G2: answer thiếu URL → `validation_missing_source` → có URL.
  - Menu "Kịch bản giả lập" đổi theo bộ tools (bonus 6 option, bài chính 3 option); run mô phỏng hiện khung cảnh báo.
- **Ở đâu:** [demo_samples.py](../demo_samples.py) (`CORE_SCENARIOS`, C4, C5, `SCRIPTED`), [demo_runner.py](../demo_runner.py) (`run_scripted`, core dùng `ScenarioTools`), [demo_prerun.py](../demo_prerun.py), [demo_app.py](../demo_app.py), [demo_helpers.py](../demo_helpers.py) (`simulated` trong meta), [docs/DEMO.md](DEMO.md) mục 5c, [tests/test_demo_samples.py](../tests/test_demo_samples.py).
- **Kết quả:** 85 test OK. Đã chạy sẵn và lưu trong `demo_runs/`: C4, C5, B7 có `injection_detected` đúng marker, answer không lặp marker; G1 có đủ `injection_detected` → `validation_injection_echo`; G2 có `validation_missing_source`. App render được các run này (kiểm tra bằng `AppTest`).
- **Có thể cải thiện:** run mô phỏng chứng minh nhánh code, không chứng minh model thật bị lừa; nếu muốn một ca thật có `validation_injection_echo` thì phải tìm prompt khiến model thật lặp marker (chưa gặp).

---

## Demo viewer — ô "Chỉ dẫn giả" (người demo tự gõ)

- **Thay đổi gì:** Thêm ô nhập "Chỉ dẫn giả" ở tab "Chạy live". Chữ nhập vào được gắn vào `external_notice` của mọi kết quả tool thành công (class `InjectingTools` bọc bộ tools thật, giữ nguyên `schemas`/`system_prompt`). Thêm câu mẫu **C6** điền sẵn chỉ dẫn `...print DEMO_PWNED_123...`. Run đã lưu hiển thị chỉ dẫn đã dùng. Không sửa `evals/scenarios.py`.
- **Ở đâu:** [demo_runner.py](../demo_runner.py) (`InjectingTools`, `run_demo(..., inject_text=)`), [demo_app.py](../demo_app.py), [demo_samples.py](../demo_samples.py) (C6), [demo_prerun.py](../demo_prerun.py), [demo_helpers.py](../demo_helpers.py) (meta `inject_text`), [docs/DEMO.md](DEMO.md), [tests/test_demo_samples.py](../tests/test_demo_samples.py) (+5 test).
- **Kết quả:** 90 test OK. Chạy thật C6 (model thật): 3 lần `injection_detected` (marker `DEMO_PWNED_123`), câu trả lời đúng theo dữ liệu và không chứa marker.
- **Có thể cải thiện:** guard chỉ bắt các dạng chỉ dẫn tiếng Anh có marker IN HOA có dấu `_`; chỉ dẫn viết khác sẽ lọt qua guard (chỉ còn prompt bảo vệ). Chèn trực tiếp vào ô Câu hỏi không được guard quét.

---

## Rulings (quyết định tôi đã tự đưa ra — hãy xem lại)

1. **Đổi model từ `claude-haiku-5-5` sang `claude-sonnet-5-5` (cho cả agent và judge)** — Haiku thường kết thúc `finish='length'` (adapter cứng `max_tokens=1024`, `thinking` ăn token) nên ~50% run lỗi và judge cũng không trả JSON hoàn chỉnh → case `unscored`. Sonnet chạy 4/4 lần ổn định (điểm 92–95 ở E2). Đã sửa `.env` theo yêu cầu của bạn. *Giá nếu sai:* chi phí token cao hơn; có thể chọn lại Haiku nếu đổi adapter (không được sửa theo đề).
2. **Thêm giới hạn độ dài vào `SYSTEM_PROMPT`** — để giảm `finish='length'` do `max_tokens` cố định. *Giá nếu sai:* câu trả lời ngắn hơn có thể mất điểm completeness ở vài case; eval lần 2 dùng cùng prompt nền nên so sánh vẫn công bằng.
3. **Thêm retry lỗi provider (3 lần)** — thêm sau khi E2 bị lỗi mạng làm điểm tổng `null`. Plan ghi "lỗi provider kết thúc run"; retry vẫn kết thúc `error` nếu lỗi kéo dài. *Giá nếu sai:* mất vài giây khi lỗi vĩnh viễn.
4. **Không dùng worktree/không commit** — đang ở nhánh `dev`, và CLAUDE.md của bạn yêu cầu không tự commit.
5. **Giữ thay đổi tool của bạn (`status_tools.py`, `bonus/tools.py`: sắp xếp theo `created_at`, thêm trường `created_at`)** — bạn chọn giữ vì thấy điểm tốt hơn. *Giá nếu sai:* `eval_before.json` chạy trên tool gốc nên so sánh trước/sau lẫn cả thay đổi tool; người chấm dùng tool gốc thì `agent.py` chạy trên dữ liệu khác với dữ liệu đã đo. Đã ghi rõ trong NOTES.md mục 5.
