# Spec: Status Investigation Agent (ReAct loop)

Nguồn: README.md, GUIDE.md, RUBRIC.md, RULES.md, CHECKPOINTS.md, SUBMISSION.md, NOTES.md và các tests trong `tests/`, `bonus/`.

## 1. Mục tiêu

Hoàn thiện `run_agent` trong `agent.py` (Python stdlib, **không dùng framework agent**) để LLM gọi tools tra cứu GitHub/Cloudflare Status, sau đó chạy eval 22 case hai lần (trước/sau cải tiến), phân tích lỗi trong `NOTES.md`. Tuỳ chọn: bonus 5 provider (+15 điểm).

Điểm: bài chính 85 (agent loop 30, robustness/trace 15, eval + phân tích 20, cải tiến + trình bày 20); bonus tối đa 15.

## 2. Hợp đồng `run_agent`

`run_agent(question, provider, tools, max_steps=6) -> dict`

| Yêu cầu | Chi tiết |
|---|---|
| Messages ban đầu | `system` (SYSTEM_PROMPT) + `user` (question) |
| Gọi model | `provider.complete(messages, SCHEMAS)` → `message, calls, finish, usage`; mỗi lần gọi = 1 step |
| Assistant message | Append **nguyên vẹn** vào `messages` trước tool results |
| Tool call | Mỗi call `{id, name, arguments(JSON string)}`; parse → `tools.execute(name, args)` |
| Tool result | `{'role':'tool','tool_call_id':id,'content':json_string}`; xử lý **mọi** call trước lần gọi model kế |
| Dừng | `finish=='stop'` và không còn calls → `completed`. `length`/lý do lạ → `error` |
| Kết quả | `status` ∈ {completed, max_steps, error}, `answer` (str), `trace` (list), `usage` (list), tuỳ chọn `error` |
| Trace | Mọi phần tử có key `event`. Tool call: `{'event':'tool','step':n,'name','arguments','result'}`. Không ghi key/API secret, không yêu cầu chain-of-thought |

## 3. Xử lý lỗi (Bài 2)

- Hết `max_steps` → `max_steps`.
- JSON arguments lỗi (hoặc không phải object) → tool result `{"ok":false,"error":"INVALID_ARGUMENTS",...}` gửi lại model, không crash.
- Tool không tồn tại / provider không hợp lệ / timeout → đã được `tools.execute` chuyển thành observation `{ok:false}`; vẫn đưa vào trace, model được báo cáo thiếu dữ liệu. Exception bất ngờ từ `tools.execute` cũng bắt và chuyển thành observation.
- `provider.complete` ném lỗi → `status='error'`, ghi `error`, không crash.
- Lỗi tool = observation; lỗi provider/truncation = kết thúc run.

## 4. Kiểm tra nguồn (Bài 4, `tests/test_validation.py`)

- Lưu `url` từ các `get_incident_details` thành công (`ok` true).
- Final answer không chứa URL nào đã quan sát → ghi trace `validation_missing_source`, thêm user message yêu cầu bổ sung nguồn, tiếp tục nếu còn step.
- Hết step khi đang thiếu nguồn → `max_steps` (không `completed`).
- Không có incident thành công → không yêu cầu URL.

## 5. Eval & phân tích (Bài 3–5)

- `evals/run_evals.py --output eval_before.json` (22 case, `summary.score_0_100` ≠ null) **trước** khi thêm validation nguồn / cải tiến.
- Chọn một lỗi từ trace (gợi ý nhóm: A2/A8 nguồn-scope, A3/A4/H5/H7 timeout & injection, H1/H6 nhiều bước/dữ liệu dài, H2/H3/H4/H8 tiền đề sai), implement cải tiến, chạy `eval_after.json` với **cùng** agent model, judge model, snapshot, max steps (khối `config` hai file giống nhau).
- `NOTES.md` đủ 5 mục dựa trên trace thật.
- Cấm sửa `fixtures/`, `evals/cases.json`, `evals/scenarios.py`, `evals/grading.py`, rubric, hoặc sửa tay kết quả eval.

## 6. Bonus (tuỳ chọn, +15)

- Dùng `getattr(tools,'schemas',SCHEMAS)` và `getattr(tools,'system_prompt',SYSTEM_PROMPT)`; tương thích tools bài chính. Không hard-code câu trả lời/ID incident.
- RATE_LIMITED / INVALID_ARGUMENTS / timeout: trả về model, giới hạn retry, báo phần không kiểm tra được; không coi 429 là outage.
- Pagination `get_incident_details(offset>=0, limit 1..3, next_offset)`; không tuyên bố đã xem hết timeline khi còn trang.
- Lọc 160 mục nhiễu, dẫn nguồn từng provider, bỏ qua prompt injection.
- Kiểm tra: `python -m unittest discover -s bonus -p "test_*.py" -v`, `python evals/run_evals.py --bonus --output eval_bonus.json` (max-steps 16).

## 7. Ràng buộc nộp bài

- Repo `K5-L3B-DAY04-[HoVaTen]-[MSSV]-ReactLoopAgent`, public; hiện thư mục là `K5-L3B-DAY04-BuiThaiSy-2A202604002-ReactLoopAgent` (đúng mẫu).
- Nộp: `agent.py`, `eval_before.json`, `eval_after.json` (đã xoá thông tin nhạy cảm, không `null`), `NOTES.md` (5 mục), tuỳ chọn `eval_bonus.json`.
- Không commit `.env`/API key (`git ls-files | grep .env` chỉ thấy `.env.example`).
- Deadline theo ca (23:59 cùng ngày hoặc 12:00 trưa hôm sau); commit cuối trước hạn được chấm.
- Phải giải thích được toàn bộ code nộp; demo một trace nhiều bước + một lỗi agent (xem §8).
- Môi trường: Python 3.10+, có Internet và API key một provider (`PROVIDER`, `MODEL` env); trên Windows dùng `python` thay `python3`.

## 8. Demo (CP7): trace nhiều bước + một lỗi agent

### 8.1 Mục tiêu
Người xem (giảng viên, bạn học) nhìn thấy trong ~5 phút: (a) agent suy luận qua nhiều bước gọi tool tới câu trả lời có nguồn; (b) một lỗi thật của agent, nguyên nhân, cách sửa và kết quả trước/sau.

### 8.2 Các phương án đã cân nhắc

| Phương án | Ưu | Nhược | Kết luận |
|---|---|---|---|
| Langfuse | Giao diện trace chuyên nghiệp | Cần tài khoản/self-host Docker; phải gắn SDK vào `agent.py` (phá ràng buộc "stdlib, không framework" và buộc phải giải thích code ngoài); trace đẩy ra dịch vụ ngoài (rủi ro lộ dữ liệu/key); thêm điểm hỏng khi demo (mạng, quota); trace nhiều bước của bài này chỉ ~10 event nên không cần tới mức đó | **Loại** |
| Streamlit app đầy đủ (chạy agent live) | Tương tác | Demo phụ thuộc mạng + API key + latency model; nếu lỗi giữa buổi demo thì mất cả phần trình bày; lỗi agent không tái hiện ổn định | Chỉ làm **tuỳ chọn** |
| **Streamlit trace viewer, replay-first (chọn)** | Không đụng `agent.py`; đọc trace thật từ `eval_before.json`/`eval_after.json` nên ổn định, không cần mạng/key; trình bày trực quan từng step; so sánh trước/sau cạnh nhau | Thêm dependency `streamlit` chỉ cho demo; thêm 1 file ngoài danh sách nộp bắt buộc | **Chọn** |
| Fallback: in trace đẹp ra terminal (`python run.py ...`) | Không phụ thuộc gì | Kém trực quan | Dự phòng nếu Streamlit lỗi |

### 8.3 Thiết kế viewer (`demo_app.py`, ngoài `agent.py`)
- **Chỉ đọc** file eval JSON (mặc định `eval_after.json`, chọn thêm `eval_before.json`); không đọc `.env`, không in key, không sửa file eval.
- Tab 1 **Trace nhiều bước**: chọn case → hiển thị câu hỏi, `status`, điểm judge + `reason`; timeline theo step: event `model` (finish, số tool call), event `tool` (name, arguments, result rút gọn, tô đỏ khi `ok:false`), `validation_missing_source`, `error`; câu trả lời cuối + các URL được trích.
- Tab 2 **Lỗi agent (trước/sau)**: cùng một case của hai file đặt cạnh nhau: điểm, số model calls, token, trace và answer; highlight chênh lệch.
- Tab 3 **Chạy live (prompt tuỳ ý)**: một ô nhập câu hỏi (kèm vài câu mẫu lấy từ `question` của các case eval) → gọi `run_agent(question, provider, tools)` giống `run.py` → hiển thị bằng đúng bộ render trace của tab 1. Chỉ bật khi env có `PROVIDER`/`MODEL`/API key (viewer không tự đọc `.env`); không có thì hiện hướng dẫn và tab 1–2 vẫn dùng bình thường. Mỗi lần chạy live lưu vào `demo_runs/*.json` (thư mục được gitignore, đã bỏ thông tin nhạy cảm) để mở lại như replay nếu mạng hỏng.
- **Đầu vào của demo**: (a) replay = chọn một case có sẵn (câu hỏi lấy từ `evals/cases.json` qua file eval); (b) live = một chuỗi câu hỏi tự nhiên, cùng kiểu đầu vào của `run_agent(question, ...)`/`run.py`. Mặc định dùng cùng `max_steps` như eval để so sánh công bằng.
- Chiến lược demo: **replay là đường chính (đảm bảo chạy được), live là phần "hỏi thử khán giả"**; nếu live lỗi thì chuyển sang replay mà không mất mạch.
- Logic tách khỏi UI thành hàm thuần (`load_results`, `case_ids`, `trace_rows`, `summarize_run`) để test offline được.
- Kịch bản demo: (1) một case có ≥3 step/≥2 tool call hoàn thành tốt; (2) case lỗi đã chọn ở Bài 4, đối chiếu trace trước/sau; (3) nêu giới hạn (judge cùng model, một lần chạy). Chuẩn bị sẵn ảnh chụp/terminal output làm dự phòng.

### 8.4 Non-goals / anti-goals
- Không tích hợp Langfuse hay bất kỳ SDK quan sát nào vào `agent.py`.
- Không sửa dữ liệu, điểm hay trace để demo đẹp hơn; viewer không được che lỗi.
- Demo không được phụ thuộc vào việc gọi LLM live để thành công (live là phần thêm, không phải đường duy nhất).
- Viewer không được tự đọc `.env` hay hiển thị key; run lưu trong `demo_runs/` không chứa key.
