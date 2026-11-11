# Ghi chú phân tích · Day 04

Họ và tên: Bùi Thái Sỹ
MSSV: 2A202604002

## 1. Case được chọn

- ID case: **A5** (chính), kèm **E1** cùng kiểu lỗi.
- Câu hỏi A5: "Tôi cần danh sách đầy đủ tất cả incident GitHub Actions trong năm 2025... đừng bịa."
- Câu trả lời của agent (lần 1): "...các incident Actions gần đây đều được cập nhật vào tháng 11/2026. **Vì vậy, không có incident nào trong kết quả thuộc năm 2025.** Có 23 incident khớp... nhưng tôi chưa xác minh ngày bắt đầu của từng cái."
- Điểm ở lần chạy 1: A5 = **74** (factuality 28, completeness 20, evidence 15, boundaries 11); E1 = **71**. Điểm tổng lần 1 = 90.86.

## 2. Bằng chứng trong trace

Trace A5 lần 1 (`eval_before.json`) chỉ có một tool call, rồi trả lời luôn:

```text
model (step 1, finish=tool_calls)
tool  get_status {provider: github, component: Actions}   -> incidents (chỉ có id, name, status, updated_at)
model (step 2, finish=stop)  -> answer khẳng định "không có incident nào thuộc năm 2025"
```

Judge (`grade.reason`): câu trả lời "khẳng định quá mức rằng 'không có incident nào trong kết quả thuộc năm 2025'... Trace chỉ cho thấy 5 incident với trường `updated_at`, không có ngày bắt đầu, và chính câu trả lời cũng thừa nhận chưa xác minh ngày bắt đầu nên hai ý này mâu thuẫn nhau."

Trace E1 lần 1: chỉ mở 2 incident (`h02n9572mx9y`, `xr3myzj7ms51`), bỏ sót incident ngày 05/11 (`t89g2q1800fr`) mà `expected` nhắc tới, và gọi hai incident 04/11 là "liên quan nhất" khi chưa so sánh.

Nguyên nhân có thể: lỗi nằm ở **prompt và loop**, không phải giới hạn dữ liệu. Prompt gốc không cấm suy luận từ `updated_at`, không yêu cầu mở các incident mới nhất; loop không kiểm tra câu trả lời có dẫn nguồn đã quan sát hay không. (Việc "không tìm thấy ≠ không tồn tại" là giới hạn của snapshot 50 incident gần nhất, agent phải nêu chứ không được kết luận.)

## 3. Thay đổi đã thực hiện

- Sửa gì, ở đâu (`agent.py`):
  1. **Cổng kiểm tra nguồn** trong `run_agent`: lưu `url` của các `get_incident_details` thành công; nếu final answer không chứa URL nào đã quan sát thì ghi trace `validation_missing_source`, thêm user message yêu cầu dẫn URL từ tool và tiếp tục trong `max_steps` (hết step thì `max_steps`). Không có incident thành công thì không bắt URL.
  2. **Quy tắc bằng chứng trong `SYSTEM_PROMPT`**: mở các incident mới nhất bằng `get_incident_details`; `updated_at` không phải ngày bắt đầu; không gọi "liên quan nhất" khi chưa so sánh; không kết luận "không có" từ tìm kiếm rỗng hoặc giới hạn 50 incident.
  3. (Đã làm trước eval lần 1, nên áp dụng cho cả hai lần) retry tối đa 3 lần khi provider lỗi mạng; giới hạn độ dài answer trong prompt vì adapter cố định `max_tokens=1024`.
- Vì sao chọn thay đổi này: cùng một lỗi (khẳng định vượt quá bằng chứng, bỏ sót incident mới nhất) xuất hiện ở hai case thấp nhất; sửa ở prompt + cổng nguồn là thay đổi nhỏ, kiểm chứng được bằng test offline (`tests/test_validation.py`, `tests/test_robustness.py`) và không đụng tới dataset, fixtures hay grading.

## 4. So sánh hai lần chạy

Cấu hình giống hệt (đã so sánh khối `config`): provider `anthropic`, agent và judge `claude-sonnet-5-5`, `max_steps` 8, dataset `core`.

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 90.86 | 92.77 |
| Điểm case đã chọn | A5 = 74 (E1 = 71) | A5 = 83 (E1 = 89) |
| Số model calls | 57 | 64 |
| Token (input / output) | 93,726 / 13,415 | 138,984 / 17,646 |

Provider không trả chi phí tiền trong kết quả. Token input tăng ~48% vì agent mở nhiều incident hơn (A5 từ 1 lên 4 lần `get_incident_details`).

- Lỗi đã giải quyết:
  - A5: không còn kết luận "không có incident 2025"; nêu "việc không thấy chúng không chứng minh là không có", mở 4 incident mới nhất và dẫn URL từ tool.
  - E1: mở thêm `pfbmpxxfq1cy` và `t89g2q1800fr` (incident 05/11 mà `expected` nhắc tới). Cổng nguồn đã **chặn một câu trả lời có URL tự ghép từ ID** (`validation_missing_source` trong trace E1); agent tự thừa nhận "các link lần trước tôi tự ghép từ ID" và trả lời lại bằng URL của tool. Điểm 71 → 89.
- Lỗi còn lại hoặc mới xuất hiện:
  - A5 còn 83: judge vẫn trừ completeness (chỉ đọc chi tiết 4 incident).
  - Một số case giảm nhẹ: H6 91 → 85, H1 88 → 86, A3 95 → 92, H2 93 → 91, H5 93 → 91. Chênh lệch nhỏ, có thể do nhiễu của judge/model thay vì do thay đổi; chưa kiểm tra riêng từng case.
  - Cổng nguồn thêm 1 vòng model ở các case bị bắt (E1, A6): tốn token. Ở A6 còn có 1 lần `provider_retry` do lỗi mạng.

## 5. Giới hạn

- **Judge:** điểm 0–100 là ước lượng của LLM; judge dùng **cùng model** (`claude-sonnet-5-5`) với agent nên có thể thiên lệch. Judge còn lỗi ngẫu nhiên (JSON bị cắt do `max_tokens=1024` cứng, lỗi mạng) nên mỗi eval phải chạy lại nhiều lượt (lần 1: 4 lượt, lần 2: 2 lượt) mới đủ 22 case; file nộp là lượt đầy đủ cuối cùng của mỗi lần.
- **Snapshot:** dữ liệu cố định ngày 09/11/2026, 50 incident gần nhất; không phản ánh tình trạng thực tế hiện tại. Cổng nguồn chỉ kiểm tra có mặt URL đã quan sát, không chứng minh mọi claim đều có nguồn.
- **Một lần chạy mỗi phiên bản:** chênh 1.91 điểm (90.86 → 92.77) nằm trong khoảng nhiễu có thể có giữa các lần chạy; chưa chạy lặp nên không chứng minh cải thiện ổn định. Cải thiện rõ nhất ở đúng hai case được nhắm tới (E1, A5) là tín hiệu tốt nhưng vẫn chỉ là một mẫu.
- Prompt giới hạn answer ≤120 từ (do `max_tokens` của adapter) có thể làm câu trả lời thiếu chi tiết.
- **Thay đổi tool ngoài agent:** sau khi chạy `eval_before.json`/`eval_after.json`, `status_tools.py` (`get_status`) và `bonus/tools.py` được sửa để sắp xếp incident theo `created_at` giảm dần trước khi cắt top-N và trả thêm trường `created_at`. Hai file eval trên chạy với tool gốc nên mức chênh 90.86 → 92.77 chỉ phản ánh `agent.py` (prompt + cổng nguồn + retry), còn `eval_bonus.json` chạy trên tool đã sửa. Cần chạy lại `eval_before.json` trên tool đã sửa nếu muốn so sánh cùng điều kiện.
- **Guard injection bằng regex (thêm sau khi chạy các file eval):** `agent.py` quét tool result để phát hiện chỉ dẫn giả và chặn câu trả lời lặp lại marker do chỉ dẫn đó đòi in (event `injection_detected` / `validation_injection_echo`). `eval_before.json`, `eval_after.json`, `eval_bonus.json` chạy trước guard này nên không đo tác dụng của nó; chỉ có test offline và 3 lần chạy riêng A4, H5, B7 (model không lặp marker).

