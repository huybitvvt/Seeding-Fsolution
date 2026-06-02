"""Seed lead mẫu để demo Lead Hunter cho khách.

5 lead theo đúng 5 ví dụ trong đặc tả → minh hoạ đủ 5 mức: lạnh, quan tâm, ấm, nóng, rất nóng.
Điểm số set explicit đúng theo bảng điểm đặc tả để tách mức rõ ràng khi demo.

Chạy:   python seed_demo_leads.py          (thêm dữ liệu demo)
        python seed_demo_leads.py clear    (xoá dữ liệu demo)
"""
import os
import sys

os.environ.setdefault('PORT', '5097')
import app  # noqa: E402

DEMO_POST_PREFIX = 'demo_'
NOW = app.datetime.utcnow().isoformat(timespec='seconds') + 'Z'


def _hours_ago(h):
    return (app.datetime.utcnow() - app.timedelta(hours=h)).isoformat(timespec='seconds') + 'Z'


DEMO_LEADS = [
    {
        'post_id': 'demo_cold_01',
        'name': 'Nguyễn Văn Lạnh',
        'need': 'Có ai biết AppSheet là gì không?',
        'source': 'post',
        'group_id': '802942327170209',
        'post_url': 'https://facebook.com/demo/cold',
        'evidence': 'Có ai biết AppSheet là gì không?',
        'lead_score': 5,
        'score_reasons': ['Có nhắc công nghệ nhưng chưa rõ nhu cầu'],
    },
    {
        'post_id': 'demo_interested_01',
        'name': 'Trần Thị Quan Tâm',
        'need': 'Mình cần tìm hiểu phần mềm quản lý kho bằng Excel',
        'source': 'post',
        'group_id': '802942327170209',
        'post_url': 'https://facebook.com/demo/interested',
        'evidence': 'Mình cần tìm hiểu phần mềm quản lý kho bằng Excel',
        'lead_score': 25,
        'score_reasons': ['Có từ khóa nhu cầu (+10)', 'Quan tâm lĩnh vực Excel/kho (+15)'],
    },
    {
        'post_id': 'demo_warm_01',
        'name': 'Lê Văn Ấm',
        'need': 'Cần đơn vị làm AppSheet quản lý vận tải',
        'source': 'post',
        'group_id': '3809441172650624',
        'post_url': 'https://facebook.com/demo/warm',
        'evidence': 'Cần đơn vị làm AppSheet quản lý vận tải',
        'lead_score': 50,
        'score_reasons': ['Có từ khóa nhu cầu (+10)', 'Có lĩnh vực cụ thể (+10)', 'Khớp giải pháp F-Solution (+30)'],
    },
    {
        'post_id': 'demo_hot_01',
        'name': 'Phạm Thị Nóng',
        'need': 'Cần AppSheet quản lý kho triển khai trong tháng này, liên hệ gấp',
        'phone': '0901234567',
        'phones': ['0901234567'],
        'source': 'comment',
        'group_id': '3809441172650624',
        'post_url': 'https://facebook.com/demo/hot',
        'comment_url': 'https://facebook.com/demo/hot?comment=1',
        'evidence': 'Cần AppSheet quản lý kho triển khai trong tháng này, liên hệ 0901234567',
        'lead_score': 80,
        'score_reasons': ['Có từ khóa nhu cầu (+10)', 'Có số điện thoại (+30)', 'Có deadline (+20)', 'Khớp giải pháp F-Solution (+20)'],
        'lead_status': 'contacted',
        'status_history': [
            {'status': 'new', 'note': 'Lead được tạo', 'by': 'system', 'at': _hours_ago(3)},
            {'status': 'contacted', 'note': 'Sale gọi điện', 'by': 'Sale An', 'at': _hours_ago(1)},
        ],
    },
    {
        'post_id': 'demo_veryhot_01',
        'name': 'Hoàng Văn Rất Nóng',
        'need': 'Cần triển khai CRM cho công ty trong tháng này, có ngân sách, báo giá gấp',
        'phone': '0987654321',
        'phones': ['0987654321'],
        'source': 'comment',
        'group_id': '3809441172650624',
        'post_url': 'https://facebook.com/demo/veryhot',
        'comment_url': 'https://facebook.com/demo/veryhot?comment=1',
        'budget': '50 triệu',
        'evidence': 'Cần CRM, ngân sách 50 triệu, triển khai tháng này, báo giá gấp 0987654321',
        'lead_score': 90,
        'score_reasons': ['Có từ khóa nhu cầu (+10)', 'Yêu cầu báo giá (+20)', 'Có số điện thoại (+30)', 'Có deadline (+20)', 'Có ngân sách (+25) bị giới hạn'],
        'status_history': [
            {'status': 'new', 'note': 'Lead được tạo', 'by': 'system', 'at': _hours_ago(2)},
        ],
        'behavior_events': [
            {'type': 'inbox_reply', 'note': 'Khách chủ động inbox', 'by': 'system', 'at': _hours_ago(2)},
        ],
    },
]


def seed():
    with app.app.test_request_context():
        leads = [app._normalise_lead(item, item['post_id']) for item in DEMO_LEADS]
        app._merge_leads_into_memory(leads)
        ok, err = app._save_leads_to_supabase(leads)
    print('--- ĐÃ TẠO LEAD DEMO ---')
    for l in sorted(leads, key=lambda x: -x['lead_score']):
        tags = ', '.join((l.get('platform_tags') or []) + ([l['industry_module']] if l.get('industry_module') else []))
        print(f"  {l['lead_score']:>4}đ | {l['lead_level_label']:<13} | {l['name']:<20} | {tags or '—'}")
    print(f"Supabase: {'OK' if ok else 'lỗi: ' + err}")
    print('Mở web tab Lead để xem.')


def clear():
    removed = 0
    for pid in list(app._leads.keys()):
        if pid.startswith(DEMO_POST_PREFIX):
            app._leads.pop(pid, None)
            removed += 1
    app._save_leads()
    if app.SUPABASE_URL and app.SUPABASE_KEY:
        for item in DEMO_LEADS:
            try:
                app._req.delete(
                    f"{app.SUPABASE_URL.rstrip('/')}/rest/v1/{app.SUPABASE_LEAD_TABLE}",
                    headers={'apikey': app.SUPABASE_KEY, 'Authorization': f'Bearer {app.SUPABASE_KEY}'},
                    params={'post_id': f"eq.{item['post_id']}"},
                    timeout=30,
                )
            except Exception as e:
                print('Xoá Supabase lỗi:', e)
    print(f'Đã xoá {removed} nhóm lead demo (local) + Supabase.')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'clear':
        clear()
    else:
        seed()
