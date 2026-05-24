"""Supabase storage layer (PostgREST over HTTPS).

Mỗi DAO ánh xạ 1-1 với một file JSON cũ trong thư mục data/:
    groups.json              -> bảng groups
    telegram_config.json     -> bảng telegram_chat_ids
    settings.json            -> bảng app_kv (key='settings')
    ai_config.json           -> bảng app_kv (key='ai_config')
    seen_posts.json          -> bảng seen_posts
    classifications.json     -> bảng classifications

Nếu env SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY chưa được set thì
`is_enabled()` trả về False, app sẽ tự fallback về JSON file.
"""

import os
import json
from typing import Any, Optional
from urllib.parse import quote

import requests
from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BASE_DIR, '.env'), override=True)

SUPABASE_URL = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
SUPABASE_KEY = (
    os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    or os.environ.get('SUPABASE_ANON_KEY')
    or os.environ.get('SUPABASE_PUBLISHABLE_KEY')
    or os.environ.get('VITE_SUPABASE_PUBLISHABLE_KEY')
    or ''
)
STAFF_USERS_TABLE = os.environ.get('SUPABASE_STAFF_TABLE', 'staff_users')
MANAGED_CHANNEL_TABLE = os.environ.get('SUPABASE_CHANNEL_TABLE', 'managed_channels')

_TIMEOUT = 30


def is_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(prefer: str = 'return=representation') -> dict:
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': prefer,
    }


def _url(path: str) -> str:
    return f'{SUPABASE_URL}/rest/v1/{path.lstrip("/")}'


def _request(method: str, path: str, **kwargs) -> requests.Response:
    if not is_enabled():
        raise RuntimeError('Supabase chưa được cấu hình (thiếu SUPABASE_URL/KEY)')
    headers = kwargs.pop('headers', None) or _headers(kwargs.pop('prefer', 'return=representation'))
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            r = requests.request(method, _url(path), headers=headers, timeout=_TIMEOUT, **kwargs)
            if r.status_code >= 400:
                raise RuntimeError(f'Supabase {method} {path} {r.status_code}: {r.text}')
            return r
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            continue
    raise RuntimeError(f'Supabase {method} {path} network error: {last_err}')


def ping() -> dict:
    """Kiểm tra kết nối nhanh."""
    if not is_enabled():
        return {'ok': False, 'error': 'Chưa cấu hình SUPABASE_URL/KEY'}
    try:
        r = requests.get(
            f'{SUPABASE_URL}/rest/v1/',
            headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
            timeout=_TIMEOUT,
        )
        return {'ok': r.status_code < 500, 'status': r.status_code}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ── groups ──────────────────────────────────────────────
def list_groups() -> list:
    r = _request('GET', 'groups?select=id,name&order=created_at.asc')
    return r.json()


def upsert_group(gid: str, name: str = '') -> None:
    _request('POST', 'groups', json=[{'id': gid, 'name': name}],
             prefer='resolution=merge-duplicates,return=minimal')


def delete_group(gid: str) -> None:
    _request('DELETE', f'groups?id=eq.{gid}', prefer='return=minimal')


# ── telegram_chat_ids ───────────────────────────────────
def list_chat_ids() -> list:
    r = _request('GET', 'telegram_chat_ids?select=chat_id&order=created_at.asc')
    return [row['chat_id'] for row in r.json()]


def add_chat_id(cid: str) -> None:
    _request('POST', 'telegram_chat_ids', json=[{'chat_id': cid}],
             prefer='resolution=ignore-duplicates,return=minimal')


def remove_chat_id(cid: str) -> None:
    _request('DELETE', f'telegram_chat_ids?chat_id=eq.{cid}', prefer='return=minimal')


# ── app_kv (settings / ai_config) ───────────────────────
def kv_get(key: str, default: Any = None) -> Any:
    r = _request('GET', f'app_kv?select=value&key=eq.{key}&limit=1')
    rows = r.json()
    return rows[0]['value'] if rows else default


def kv_set(key: str, value: Any) -> None:
    _request('POST', 'app_kv', json=[{'key': key, 'value': value}],
             prefer='resolution=merge-duplicates,return=minimal')


# ── staff_users ─────────────────────────────────────────
def get_staff_user(username: str, table: Optional[str] = None) -> Optional[dict]:
    """Read one login user from Supabase.

    The customer-facing login is intentionally simple: one table with username
    and password columns. Cookie fields are optional and used only after login.
    """
    username = (username or '').strip().lower()
    if not username:
        return None
    table_name = table or STAFF_USERS_TABLE
    encoded = quote(username, safe='')
    r = _request('GET', f'{table_name}?select=*&username=eq.{encoded}&limit=1')
    rows = r.json()
    return rows[0] if rows else None


def list_staff_users(table: Optional[str] = None) -> list:
    table_name = table or STAFF_USERS_TABLE
    r = _request(
        'GET',
        f'{table_name}?select=id,name,username,role,cookie,facebook_user_id,'
        'enabled,created_at,updated_at&enabled=eq.true&order=created_at.asc',
    )
    return r.json()


def insert_staff_user(row: dict, table: Optional[str] = None) -> dict:
    table_name = table or STAFF_USERS_TABLE
    r = _request('POST', table_name, json=[row], prefer='return=representation')
    rows = r.json()
    return rows[0] if rows else {}


def update_staff_user(username: str, row: dict, table: Optional[str] = None) -> dict:
    table_name = table or STAFF_USERS_TABLE
    username = (username or '').strip().lower()
    if not username:
        return {}
    r = _request(
        'PATCH',
        f'{table_name}?username=eq.{quote(username, safe="")}',
        json=row,
        prefer='return=representation',
    )
    rows = r.json()
    return rows[0] if rows else {}


def delete_staff_user(staff_id: str = '', username: str = '', table: Optional[str] = None) -> None:
    table_name = table or STAFF_USERS_TABLE
    staff_id = (staff_id or '').strip()
    username = (username or '').strip().lower()
    if staff_id:
        r = _request('DELETE', f'{table_name}?id=eq.{quote(staff_id, safe="")}', prefer='return=representation')
        if r.json():
            return
        _request(
            'PATCH',
            f'{table_name}?id=eq.{quote(staff_id, safe="")}',
            json={'enabled': False},
            prefer='return=minimal',
        )
        return
    if username:
        r = _request('DELETE', f'{table_name}?username=eq.{quote(username, safe="")}', prefer='return=representation')
        if r.json():
            return
        _request(
            'PATCH',
            f'{table_name}?username=eq.{quote(username, safe="")}',
            json={'enabled': False},
            prefer='return=minimal',
        )
        return


# ── managed_channels ───────────────────────────────────
def list_managed_channels(table: Optional[str] = None) -> list:
    table_name = table or MANAGED_CHANNEL_TABLE
    r = _request(
        'GET',
        f'{table_name}?select=id,platform,channel_name,channel_type,link,target_id,'
        'note,created_at,updated_at&order=created_at.desc',
    )
    return r.json()


def upsert_managed_channel(row: dict, table: Optional[str] = None) -> dict:
    table_name = table or MANAGED_CHANNEL_TABLE
    r = _request(
        'POST',
        table_name,
        json=[row],
        prefer='resolution=merge-duplicates,return=representation',
    )
    rows = r.json()
    return rows[0] if rows else {}


def update_managed_channel(channel_id: str, row: dict, table: Optional[str] = None) -> dict:
    table_name = table or MANAGED_CHANNEL_TABLE
    r = _request(
        'PATCH',
        f'{table_name}?id=eq.{quote(channel_id or "", safe="")}',
        json=row,
        prefer='return=representation',
    )
    rows = r.json()
    return rows[0] if rows else {}


def delete_managed_channel(channel_id: str, table: Optional[str] = None) -> None:
    table_name = table or MANAGED_CHANNEL_TABLE
    _request('DELETE', f'{table_name}?id=eq.{quote(channel_id or "", safe="")}', prefer='return=minimal')


# ── seen_posts ──────────────────────────────────────────
def list_seen_post_ids() -> set:
    rows: list = []
    offset = 0
    page = 1000
    while True:
        r = _request('GET',
                     f'seen_posts?select=post_id&order=post_id.asc'
                     f'&offset={offset}&limit={page}')
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return {row['post_id'] for row in rows}


def add_seen_post_ids(post_ids) -> None:
    ids = list({pid for pid in post_ids if pid})
    if not ids:
        return
    payload = [{'post_id': pid} for pid in ids]
    chunk = 500
    for i in range(0, len(payload), chunk):
        _request('POST', 'seen_posts', json=payload[i:i + chunk],
                 prefer='resolution=ignore-duplicates,return=minimal')


def upsert_posts(posts) -> None:
    """Lưu/đè metadata cho danh sách bài viết.

    Mỗi post là dict có ít nhất `id`; các trường khác (message, permalink_url,
    created_time, from.name, _group_id) được trích nếu có.
    """
    rows = []
    for p in posts or []:
        pid = p.get('id')
        if not pid:
            continue
        created = p.get('created_time') or None
        from_obj = p.get('from') or {}
        rows.append({
            'post_id': pid,
            'permalink_url': p.get('permalink_url') or None,
            'group_id': p.get('_group_id') or None,
            'author_name': (from_obj.get('name') if isinstance(from_obj, dict) else None) or None,
            'message': p.get('message') or None,
            'created_time': created,
        })
    if not rows:
        return
    chunk = 200
    for i in range(0, len(rows), chunk):
        _request('POST', 'seen_posts', json=rows[i:i + chunk],
                 prefer='resolution=merge-duplicates,return=minimal')


def list_saved_posts(limit: int = 100, group_id: Optional[str] = None) -> list:
    """Trả danh sách bài đã lưu, sắp xếp theo created_time DESC."""
    limit = max(1, min(int(limit), 500))
    params = (
        'seen_posts?select=post_id,permalink_url,group_id,author_name,message,'
        'created_time,seen_at'
        f'&order=created_time.desc.nullslast&limit={limit}'
    )
    if group_id:
        params += f'&group_id=eq.{group_id}'
    r = _request('GET', params)
    return r.json()


# ── classifications ─────────────────────────────────────
def list_classifications() -> dict:
    rows: list = []
    offset = 0
    page = 1000
    while True:
        r = _request('GET',
                     f'classifications?select=post_id,category'
                     f'&offset={offset}&limit={page}')
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return {row['post_id']: row['category'] for row in rows}


def upsert_classifications(items: dict) -> None:
    if not items:
        return
    payload = [{'post_id': pid, 'category': cat} for pid, cat in items.items() if pid]
    chunk = 500
    for i in range(0, len(payload), chunk):
        _request('POST', 'classifications', json=payload[i:i + chunk],
                 prefer='resolution=merge-duplicates,return=minimal')
