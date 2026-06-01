# Lead Hunter_F.Solution Bridge

Extension này dùng để gửi bình luận TikTok và lấy cookie Facebook khi admin bấm nút trên web bằng chính phiên đăng nhập Chrome của khách. Web không tự đọc cookie nền; extension chỉ trả cookie khi người dùng chủ động bấm.

## Cài đặt cho khách

1. Mở Chrome và vào `chrome://extensions`.
2. Bật `Developer mode`.
3. Chọn `Load unpacked`.
4. Chọn thư mục `browser-extension` trong source dự án.
5. Đăng nhập TikTok/Facebook trên Chrome.
6. Mở web Phần mềm Lead Hunter_F.Solution:
   - Vào `Lead` hoặc `TikTok CMT`, chọn video và bấm `Gửi CMT TikTok`.
   - Vào `Quản lý Cooki` -> thêm/sửa nhân sự -> bấm `Lấy từ Chrome` để lấy cookie Facebook.

## Lưu ý vận hành

- Không cần dán cookie TikTok vào web để gửi comment.
- Facebook cookie chỉ được lấy khi admin bấm nút, không tự động thu thập nền.
- Nếu TikTok hỏi đăng nhập lại, hãy đăng nhập trực tiếp trên tab TikTok rồi bấm gửi lại.
- Extension chỉ gửi khi người dùng bấm nút, không có chế độ tự spam hoặc chạy nền hàng loạt.
