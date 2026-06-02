import os
import json
import threading
import time as _time
import re
import uuid
import hashlib
import secrets
import requests as _req
from html import unescape
from datetime import datetime, time, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

from core.group_api import FacebookGroupAPI, load_token, load_cookie, refresh_token
from core.ai_classifier import AIClassifier, DEFAULT_MODEL, DEFAULT_API_KEY, DEFAULT_CATEGORIES, PROVIDERS, extract_phones
from core import supabase_store as sb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)
RUNTIME_DATA_DIR = os.environ.get('RUNTIME_DATA_DIR') or ('/tmp/seeding-fsolution' if os.environ.get('VERCEL') else DATA_DIR)

SEEN_FILE = os.path.join(DATA_DIR, 'seen_posts.json')
TG_CONFIG_FILE = os.path.join(DATA_DIR, 'telegram_config.json')
GROUPS_FILE = os.path.join(DATA_DIR, 'groups.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
AI_CONFIG_FILE = os.path.join(DATA_DIR, 'ai_config.json')
CLASSIFICATIONS_FILE = os.path.join(DATA_DIR, 'classifications.json')
LEADS_FILE = os.path.join(DATA_DIR, 'leads.json')
REPLY_SUGGESTIONS_FILE = os.path.join(DATA_DIR, 'reply_suggestions.json')
BUSINESS_PROFILE_FILE = os.path.join(DATA_DIR, 'business_profile.json')
STAFF_COOKIES_FILE = os.path.join(DATA_DIR, 'staff_cookies.json')
STAFF_TOKEN_DIR = os.path.join(RUNTIME_DATA_DIR, 'staff_tokens')
COMMENT_LOGS_FILE = os.path.join(DATA_DIR, 'comment_logs.json')
COMMENT_SUMMARIES_FILE = os.path.join(DATA_DIR, 'comment_summaries.json')
POST_COMMENTS_FILE = os.path.join(DATA_DIR, 'post_comments.json')
MANAGED_CHANNELS_FILE = os.path.join(DATA_DIR, 'managed_channels.json')
TIKTOK_CONFIG_FILE = os.path.join(DATA_DIR, 'tiktok_config.json')
CONTENT_PIPELINE_FILE = os.path.join(DATA_DIR, 'content_pipeline.json')

BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '')
DEFAULT_GROUP = os.environ.get('DEFAULT_GROUP', '')
PORT = int(os.environ.get('PORT', 5000))
WEB_UI_URL = (os.environ.get('WEB_UI_URL') or 'http://localhost:3000').rstrip('/')
USE_LEGACY_UI = os.environ.get('USE_LEGACY_UI', '').lower() in ('1', 'true', 'yes')
SUPABASE_URL = os.environ.get('SUPABASE_URL') or os.environ.get('VITE_SUPABASE_URL', '')
SUPABASE_KEY = (
    os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    or os.environ.get('SUPABASE_PUBLISHABLE_KEY')
    or os.environ.get('VITE_SUPABASE_PUBLISHABLE_KEY', '')
)
SUPABASE_REPLY_TABLE = os.environ.get('SUPABASE_REPLY_TABLE', 'ai_reply_suggestions')
SUPABASE_PROFILE_TABLE = os.environ.get('SUPABASE_PROFILE_TABLE', 'business_profiles')
SUPABASE_COMMENT_LOG_TABLE = os.environ.get('SUPABASE_COMMENT_LOG_TABLE', 'comment_logs')
SUPABASE_COMMENT_SUMMARY_TABLE = os.environ.get('SUPABASE_COMMENT_SUMMARY_TABLE', 'post_comment_summaries')
SUPABASE_POST_COMMENT_TABLE = os.environ.get('SUPABASE_POST_COMMENT_TABLE', 'post_comments')
SUPABASE_LEAD_TABLE = os.environ.get('SUPABASE_LEAD_TABLE', 'leads')
SUPABASE_STAFF_TABLE = os.environ.get('SUPABASE_STAFF_TABLE', 'staff_users')
SUPABASE_CHANNEL_TABLE = os.environ.get('SUPABASE_CHANNEL_TABLE', 'managed_channels')
SUPABASE_COMMENT_IMAGE_BUCKET = os.environ.get('SUPABASE_COMMENT_IMAGE_BUCKET', 'comment-images')
APP_TIMEZONE = os.environ.get('APP_TIMEZONE', 'Asia/Ho_Chi_Minh')
TIKTOK_COOKIE = os.environ.get('TIKTOK_COOKIE', '')
SIMPLE_LOGIN_ONLY = os.environ.get('SIMPLE_LOGIN_ONLY', 'true').lower() not in ('0', 'false', 'no')
MAX_COMMENT_IMAGE_BYTES = int(os.environ.get('MAX_COMMENT_IMAGE_BYTES', 8 * 1024 * 1024))
ALLOWED_COMMENT_IMAGE_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif',
}

app = Flask(__name__, template_folder='views')
app.secret_key = os.environ.get('APP_SECRET_KEY', 'seeding-fsolution-local-dev-secret-change-me')

_cors_origins = [
    o.strip()
    for o in os.environ.get(
        'CORS_ORIGINS',
        r'http://localhost:3000,http://127.0.0.1:3000,https://.*\.vercel\.app',
    ).split(',')
    if o.strip()
]
CORS(app, resources={r'/api/*': {'origins': _cors_origins, 'supports_credentials': True}})

# ── State ──────────────────────────────────────────────
_api_cache: dict = {}
_seen_ids: set = set()
_tg_chat_ids: list = []
_pages_cache: dict = {}  # {page_id: {name, access_token}}
_groups: list = []       # [{id, name}]
_settings: dict = {}    # {auto_refresh, interval}
_ai_config: dict = {}   # {provider, model, keys, auto_classify, categories}
_classifications: dict = {}  # {post_id: category}
_leads: dict = {}       # {post_id: [lead]}
_reply_suggestions: dict = {}  # {post_id: latest suggestion}
_business_profile: dict = {}  # {business_name, phone, address, why_choose_us, extra_notes}
_staff_cookies: dict = {}  # {active_staff_id, staff: [{id, name, cookie, enabled}]}
_session_staff_cache: dict = {}  # server-only cache for Supabase staff cookies
_comment_logs: list = []
_comment_summaries: dict = {}
_post_comments: list = []
_managed_channels: list = []
_tiktok_config: dict = {}
_content_pipeline: dict = {}
_scan_counter: dict = {}  # {YYYY-MM-DD: số bài quét được trong ngày}


def _default_business_profile() -> dict:
    return {
        'business_name': '',
        'phone': '',
        'address': '',
        'why_choose_us': '',
        'extra_notes': '',
    }


USE_SUPABASE = sb.is_enabled()


def _read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _default_ai_config():
    return {
        'provider': 'gemini',
        'model': DEFAULT_MODEL,
        'keys': {'gemini': DEFAULT_API_KEY, 'openai': '', 'claude': ''},
        'auto_classify': False,
        'categories': DEFAULT_CATEGORIES,
    }


def _default_staff_cookies() -> dict:
    return {'active_staff_id': '', 'staff': []}


def _default_tiktok_config() -> dict:
    return {'cookie': '', 'updated_at': '', 'updated_by': ''}


def _default_content_pipeline() -> dict:
    return {
        'sources': [
            {'id': 'techcrunch', 'name': 'TechCrunch', 'type': 'rss', 'rss_url': 'https://techcrunch.com/feed/', 'active': True},
            {'id': 'crunchbase', 'name': 'Crunchbase News', 'type': 'rss', 'rss_url': 'https://news.crunchbase.com/feed/', 'active': True},
            {'id': 'techstartups', 'name': 'TechStartups', 'type': 'rss', 'rss_url': 'https://techstartups.com/feed/', 'active': True},
        ],
        'articles': [],
        'posts': [],
    }


def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 120000)
    return salt, digest.hex()


def _verify_password(password: str, salt: str, digest: str) -> bool:
    if not password or not salt or not digest:
        return False
    _, candidate = _hash_password(password, salt)
    return secrets.compare_digest(candidate, digest)


def _load_state():
    global _seen_ids, _tg_chat_ids, _groups, _settings, _ai_config, _classifications, _leads, _reply_suggestions, _business_profile, _staff_cookies, _comment_logs, _comment_summaries, _post_comments, _managed_channels, _tiktok_config, _content_pipeline
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError as e:
        print(f'[storage] data dir is read-only, using Supabase/runtime storage: {e}')
    try:
        os.makedirs(STAFF_TOKEN_DIR, exist_ok=True)
    except OSError as e:
        print(f'[storage] token dir unavailable, token cache disabled: {e}')

    loaded_from_supabase = False
    if USE_SUPABASE:
        try:
            _seen_ids = set(sb.list_seen_post_ids())
            _tg_chat_ids = sb.list_chat_ids() or ['7129448686']
            _groups = sb.list_groups() or [{'id': DEFAULT_GROUP, 'name': ''}]
            _settings = sb.kv_get('settings', None) or {'auto_refresh': True, 'interval': 5}
            _ai_config = sb.kv_get('ai_config', None) or _default_ai_config()
            _tiktok_config = {**_default_tiktok_config(), **(sb.kv_get('tiktok_config', None) or {})}
            _classifications = sb.list_classifications()
            try:
                _managed_channels = sb.list_managed_channels(SUPABASE_CHANNEL_TABLE)
            except Exception as e:
                print(f'[supabase] load managed_channels failed, fallback file: {e}')
                _managed_channels = _read_json(MANAGED_CHANNELS_FILE, [])
            _leads = _read_json(LEADS_FILE, {})
            _reply_suggestions = _read_json(REPLY_SUGGESTIONS_FILE, {})
            loaded_profile = _read_json(BUSINESS_PROFILE_FILE, {})
            _business_profile = {**_default_business_profile(), **loaded_profile}
            profile_sb, _ = _load_business_profile_from_supabase()
            if profile_sb:
                _business_profile = {**_business_profile, **profile_sb}
            print('[supabase] state loaded from Supabase')
            loaded_from_supabase = True
        except Exception as e:
            print(f'[supabase] load failed, fallback file: {e}')

    if not loaded_from_supabase:
        _seen_ids = set(_read_json(SEEN_FILE, []))
        cfg = _read_json(TG_CONFIG_FILE, {})
        _tg_chat_ids = cfg.get('chat_ids') or ([cfg['chat_id']] if cfg.get('chat_id') else ['7129448686'])
        _groups = _read_json(GROUPS_FILE, [{'id': DEFAULT_GROUP, 'name': ''}])
        _settings = _read_json(SETTINGS_FILE, {'auto_refresh': True, 'interval': 5})
        _ai_config = _read_json(AI_CONFIG_FILE, _default_ai_config())
        _tiktok_config = {**_default_tiktok_config(), **_read_json(TIKTOK_CONFIG_FILE, {})}
        _classifications = _read_json(CLASSIFICATIONS_FILE, {})
        _managed_channels = _read_json(MANAGED_CHANNELS_FILE, [])
        _leads = _read_json(LEADS_FILE, {})
        _reply_suggestions = _read_json(REPLY_SUGGESTIONS_FILE, {})
        loaded_profile = _read_json(BUSINESS_PROFILE_FILE, {})
        _business_profile = {**_default_business_profile(), **loaded_profile}

    loaded_staff = _read_json(STAFF_COOKIES_FILE, _default_staff_cookies())
    _staff_cookies = {**_default_staff_cookies(), **loaded_staff}
    if not isinstance(_staff_cookies.get('staff'), list):
        _staff_cookies['staff'] = []
    changed_staff = False
    for item in _staff_cookies['staff']:
        if 'role' not in item:
            item['role'] = 'staff'
            changed_staff = True
        if 'username' not in item:
            item['username'] = re.sub(r'\W+', '_', (item.get('name') or item.get('id') or '')).strip('_').lower()
            changed_staff = True
    if _staff_cookies['staff'] and not any(item.get('role') == 'admin' for item in _staff_cookies['staff']):
        _staff_cookies['staff'][0]['role'] = 'admin'
        changed_staff = True
    if changed_staff:
        _save_staff_cookies()

    _comment_logs = _read_json(COMMENT_LOGS_FILE, [])
    if not isinstance(_comment_logs, list):
        _comment_logs = []
    _comment_summaries = _read_json(COMMENT_SUMMARIES_FILE, {})
    if not isinstance(_comment_summaries, dict):
        _comment_summaries = {}
    _post_comments = _read_json(POST_COMMENTS_FILE, [])
    if not isinstance(_post_comments, list):
        _post_comments = []
    if not isinstance(_managed_channels, list):
        _managed_channels = []
    if not isinstance(_tiktok_config, dict):
        _tiktok_config = _default_tiktok_config()
    loaded_pipeline = _read_json(CONTENT_PIPELINE_FILE, {})
    if USE_SUPABASE:
        try:
            loaded_pipeline = sb.kv_get('content_pipeline', loaded_pipeline) or loaded_pipeline
        except Exception as e:
            print(f'[supabase] load content_pipeline failed, fallback file: {e}')
    default_pipeline = _default_content_pipeline()
    loaded_sources = loaded_pipeline.get('sources') if isinstance(loaded_pipeline.get('sources'), list) else default_pipeline['sources']
    sources = [
        source for source in loaded_sources
        if not (
            str(source.get('id') or '').lower() == 'a16z'
            and 'a16z.com/feed' in str(source.get('rss_url') or source.get('url') or '')
        )
    ]
    if not sources:
        sources = default_pipeline['sources']
    _content_pipeline = {
        'sources': sources,
        'articles': loaded_pipeline.get('articles') if isinstance(loaded_pipeline.get('articles'), list) else [],
        'posts': loaded_pipeline.get('posts') if isinstance(loaded_pipeline.get('posts'), list) else [],
    }


def _save_seen(new_posts=None):
    """Lưu file seen_posts.json và đẩy metadata bài viết mới lên Supabase.

    `new_posts` là list dict bài mới (đã có `_group_id`, `permalink_url`...).
    """
    _write_json(SEEN_FILE, list(_seen_ids))
    if USE_SUPABASE and new_posts:
        try:
            sb.upsert_posts(new_posts)
        except Exception as e:
            print(f'[supabase] save_seen failed: {e}')


def _save_tg():
    _write_json(TG_CONFIG_FILE, {'chat_ids': _tg_chat_ids})


def _save_groups():
    _write_json(GROUPS_FILE, _groups)


def _save_settings():
    _write_json(SETTINGS_FILE, _settings)
    if USE_SUPABASE:
        try:
            sb.kv_set('settings', _settings)
        except Exception as e:
            print(f'[supabase] save_settings failed: {e}')


def _save_ai_config():
    _write_json(AI_CONFIG_FILE, _ai_config)
    if USE_SUPABASE:
        try:
            sb.kv_set('ai_config', _ai_config)
        except Exception as e:
            print(f'[supabase] save_ai_config failed: {e}')


def _save_tiktok_config():
    _write_json(TIKTOK_CONFIG_FILE, _tiktok_config)
    if USE_SUPABASE:
        try:
            sb.kv_set('tiktok_config', _tiktok_config)
        except Exception as e:
            print(f'[supabase] save_tiktok_config failed: {e}')


def _save_content_pipeline():
    _write_json(CONTENT_PIPELINE_FILE, _content_pipeline)
    if USE_SUPABASE:
        try:
            sb.kv_set('content_pipeline', _content_pipeline)
        except Exception as e:
            print(f'[supabase] save content_pipeline failed: {e}')


def _strip_html(text: str, limit: int = 600) -> str:
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = unescape(re.sub(r'\s+', ' ', text)).strip()
    return text[:limit].rstrip() + ('...' if len(text) > limit else '')


def _pipeline_article_id(url: str, title: str = '') -> str:
    seed = (url or title or str(uuid.uuid4())).strip()
    return hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]


def _pipeline_post_id(article_id: str, fmt: str) -> str:
    return hashlib.sha1(f'{article_id}|{fmt}|{datetime.utcnow().isoformat()}'.encode('utf-8')).hexdigest()[:12]


def _parse_iso_datetime(value: str):
    value = str(value or '').strip()
    if not value:
        return None
    try:
        if value.endswith('Z'):
            value = value[:-1] + '+00:00'
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _pipeline_post_message(post: dict) -> str:
    return '\n\n'.join([str(post.get('content') or '').strip(), str(post.get('hashtags') or '').strip()]).strip()


def _page_token_from_cache(page_id: str) -> str:
    global _pages_cache
    page_id = str(page_id or '').strip()
    if not page_id:
        return ''
    cached = (_pages_cache.get(page_id) or {}).get('access_token') or ''
    if cached:
        return cached
    pages = get_api(DEFAULT_GROUP).get_pages() or []
    _pages_cache = {p['id']: {'name': p['name'], 'access_token': p['access_token']} for p in pages if p.get('id')}
    return (_pages_cache.get(page_id) or {}).get('access_token') or ''


def _publish_content_pipeline_post(post: dict, targets: list[dict]) -> dict:
    message = _pipeline_post_message(post)
    if not message:
        return {'ok': False, 'error': 'Bản nháp chưa có nội dung', 'results': []}
    results = []
    ok_count = 0
    for target in targets:
        target_type = str((target or {}).get('type') or '').strip().lower()
        target_id = str((target or {}).get('id') or '').strip()
        target_name = str((target or {}).get('name') or '').strip()
        try:
            if target_type == 'page':
                page_token = _page_token_from_cache(target_id)
                if not page_token:
                    raise RuntimeError('Không lấy được Page token')
                result = get_api(DEFAULT_GROUP).create_page_post(target_id, message, page_token)
            else:
                if not target_id:
                    raise RuntimeError('Thiếu group_id')
                page_id = str((target or {}).get('page_id') or '').strip()
                page_token = _page_token_from_cache(page_id) if page_id else None
                result = get_api(target_id).create_post(message, page_token)
            if result and result.get('id'):
                ok_count += 1
                results.append({'ok': True, 'type': target_type or 'group', 'id': target_id, 'name': target_name, 'post_id': result.get('id')})
            else:
                err = (result or {}).get('error', {}).get('message') or 'Lỗi không xác định'
                results.append({'ok': False, 'type': target_type or 'group', 'id': target_id, 'name': target_name, 'error': err})
        except Exception as e:
            results.append({'ok': False, 'type': target_type or 'group', 'id': target_id, 'name': target_name, 'error': str(e)})
    return {'ok': ok_count > 0, 'success_count': ok_count, 'failed_count': len(results) - ok_count, 'results': results}


def _rss_child_text(item, names: tuple[str, ...]) -> str:
    for name in names:
        node = item.find(name)
        if node is not None and node.text:
            return node.text.strip()
    for child in list(item):
        tag = child.tag.split('}', 1)[-1]
        if tag in names and child.text:
            return child.text.strip()
    return ''


def _fetch_pipeline_rss(source: dict, limit: int = 12) -> list[dict]:
    url = source.get('rss_url') or source.get('url')
    if not url:
        return []
    resp = _req.get(
        url,
        headers={'User-Agent': 'Mozilla/5.0 Lead Hunter F.Solution/1.0'},
        timeout=15,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
    rows = []
    for item in items[:limit]:
        title = _rss_child_text(item, ('title',))
        link = _rss_child_text(item, ('link',))
        if not link:
            link_node = item.find('{http://www.w3.org/2005/Atom}link')
            link = link_node.attrib.get('href', '') if link_node is not None else ''
        summary = _strip_html(_rss_child_text(item, ('description', 'summary', 'content', 'encoded')), 700)
        published = _rss_child_text(item, ('pubDate', 'published', 'updated'))
        published_at = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
        if published:
            try:
                published_at = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat()
            except Exception:
                published_at = published
        article_id = _pipeline_article_id(link, title)
        if title and link:
            rows.append({
                'id': article_id,
                'source_id': source.get('id') or '',
                'source_name': source.get('name') or 'RSS',
                'source_type': source.get('type') or 'rss',
                'title': _strip_html(title, 220),
                'url': link,
                'summary': summary,
                'published_at': published_at,
                'status': 'new',
                'created_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
            })
    return rows


def _pipeline_write_article(article: dict, fmt: str) -> dict:
    fmt_label = {
        'pov': 'góc nhìn chuyên gia, có quan điểm rõ',
        'info': 'bản tin ngắn, dễ hiểu',
        'case': 'case study ứng dụng thực tế',
        'howto': 'hướng dẫn từng bước',
    }.get(fmt, 'bài social ngắn')
    fallback = (
        f"{article.get('title', 'Tin mới')}\n\n"
        f"{article.get('summary', '')}\n\n"
        "Góc nhìn vận hành: chọn ý chính, liên hệ tới nhu cầu khách hàng và chốt bằng một câu hỏi mở để kéo tương tác."
    ).strip()
    hashtags = '#STReal #Marketing #AIContent'
    classifier = _get_classifier()
    if classifier.api_key:
        prompt = f"""Bạn là content marketer tiếng Việt cho Phần mềm Lead Hunter_F.Solution của F-Solution.

Viết lại tin sau thành một bài đăng Facebook/LinkedIn chuyên nghiệp.
- Format: {fmt_label}
- Giọng văn: rõ ràng, thực tế, không phóng đại.
- Có hook mở đầu, 3-5 ý chính, CTA nhẹ ở cuối.
- Không bịa số liệu ngoài dữ liệu.

TIÊU ĐỀ: {article.get('title', '')}
TÓM TẮT: {article.get('summary', '')}
LINK GỐC: {article.get('url', '')}

Trả về JSON object:
{{"content":"nội dung bài đăng", "hashtags":"3-6 hashtag liên quan"}}
CHỈ trả về JSON."""
        try:
            payload = json.loads(re.sub(r'^```(?:json)?|```$', '', classifier._call_api(prompt).strip(), flags=re.I | re.M).strip())
            content = str(payload.get('content') or '').strip()
            ai_hashtags = str(payload.get('hashtags') or '').strip()
            if content:
                return {'content': content, 'hashtags': ai_hashtags or hashtags, 'ai_error': ''}
        except Exception as e:
            return {'content': fallback, 'hashtags': hashtags, 'ai_error': str(e)}
    return {'content': fallback, 'hashtags': hashtags, 'ai_error': 'Chưa cấu hình API key AI'}


def _save_classifications(new_items=None):
    _write_json(CLASSIFICATIONS_FILE, _classifications)
    if USE_SUPABASE and new_items:
        try:
            sb.upsert_classifications(new_items)
        except Exception as e:
            print(f'[supabase] save_classifications failed: {e}')


def _save_leads():
    _write_json(LEADS_FILE, _leads)


def _lead_key(lead: dict) -> str:
    base = '|'.join([
        str(lead.get('platform') or lead.get('source_platform') or ''),
        str(lead.get('post_id') or ''),
        str(lead.get('comment_id') or lead.get('source_id') or ''),
        str(lead.get('phone') or lead.get('customer_phone') or ''),
    ]).strip('|')
    if not base:
        base = json.dumps(lead, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(base.encode('utf-8')).hexdigest()


LEAD_NEED_KEYWORDS = [
    'tôi cần', 'mình cần', 'cần hỗ trợ', 'cần xây dựng', 'cần tool', 'cần phần mềm',
    'tìm đơn vị', 'tìm người làm', 'báo giá', 'ib', 'inbox', 'quan tâm', 'đặt hàng',
]
LEAD_SOLUTION_KEYWORDS = [
    'appsheet', 'app sheet', 'google sheet', 'webapp', 'web app', 'web', 'phần mềm', 'excel',
    'bán hàng', 'khách hàng', 'crm', 'sale', 'vận đơn', 'quản lý đơn', 'hàng hóa', 'marketing',
    'kế toán', 'thuế', 'nhân sự', 'chấm công', 'kho', 'thiết bị', 'logistics', 'vận tải',
    'kho bến', 'mỹ phẩm', 'xây dựng', 'thời trang', 'nhà hàng', 'xuất nhập khẩu', 'nông sản',
]
LEAD_DEADLINE_KEYWORDS = ['deadline', 'gấp', 'ngay', 'hôm nay', 'tuần này', 'tháng này', 'trước ngày', 'triển khai trong']
LEAD_BUDGET_KEYWORDS = ['ngân sách', 'budget', 'chi phí', 'bao nhiêu', 'báo giá', 'giá']
LEAD_POSITIVE_REPLY_KEYWORDS = ['đúng rồi', 'ok', 'quan tâm', 'ib', 'inbox', 'nhắn mình', 'gửi mình', 'cho mình']

# ── Phân loại theo đặc tả: Nền tảng / Module nghiệp vụ / Module ngành ──
# Mỗi nhóm là {nhãn hiển thị: [từ khóa nhận diện]}
LEAD_PLATFORM_TAXONOMY = {
    'AppSheet': ['appsheet', 'app sheet'],
    'Google Sheet': ['google sheet', 'gsheet', 'google trang tính'],
    'WebApp': ['webapp', 'web app', 'ứng dụng web'],
    'Web': ['website', 'web'],
    'Phần mềm': ['phần mềm', 'software', 'app', 'ứng dụng'],
    'Excel': ['excel', 'bảng tính'],
}
LEAD_BUSINESS_MODULE_TAXONOMY = {
    'Bán hàng': ['bán hàng', 'sale', 'sales', 'pos'],
    'Khách hàng/CRM': ['crm', 'khách hàng', 'chăm sóc khách'],
    'Vận đơn/Quản lý đơn': ['vận đơn', 'quản lý đơn', 'đơn hàng'],
    'Hàng hóa/Kho': ['hàng hóa', 'kho', 'tồn kho', 'kho bến'],
    'Marketing': ['marketing', 'quảng cáo', 'truyền thông'],
    'Kế toán/Thuế': ['kế toán', 'thuế', 'hóa đơn', 'công nợ'],
    'Nhân sự/Chấm công': ['nhân sự', 'chấm công', 'hr', 'lương'],
    'Thiết bị': ['thiết bị', 'tài sản'],
}
LEAD_INDUSTRY_TAXONOMY = {
    'Nông sản': ['nông sản', 'nông nghiệp'],
    'Xuất nhập khẩu': ['xuất nhập khẩu', 'xnk', 'import', 'export'],
    'Logistics/Vận tải': ['logistics', 'vận tải', 'vận chuyển', 'kho bến'],
    'Mỹ phẩm': ['mỹ phẩm', 'cosmetic'],
    'Xây dựng': ['xây dựng', 'công trình', 'thi công'],
    'Thời trang': ['thời trang', 'quần áo', 'fashion'],
    'Nhà hàng/F&B': ['nhà hàng', 'quán ăn', 'f&b', 'cafe', 'cà phê'],
}


def _match_taxonomy(text: str, taxonomy: dict) -> list[str]:
    """Trả về danh sách nhãn khớp với text (ưu tiên nhãn xuất hiện trước)."""
    matched: list[str] = []
    for label, keywords in taxonomy.items():
        if any(keyword in text for keyword in keywords):
            matched.append(label)
    return matched


def _classify_lead_modules(lead: dict) -> dict:
    """Phân loại lead theo Nền tảng / Module nghiệp vụ / Module ngành (đặc tả Bước 2)."""
    text = _lead_text_blob(lead)
    platforms = _match_taxonomy(text, LEAD_PLATFORM_TAXONOMY)
    business = _match_taxonomy(text, LEAD_BUSINESS_MODULE_TAXONOMY)
    industry = _match_taxonomy(text, LEAD_INDUSTRY_TAXONOMY)
    matched_keywords = sorted({
        kw
        for group in (LEAD_NEED_KEYWORDS, LEAD_SOLUTION_KEYWORDS, LEAD_DEADLINE_KEYWORDS, LEAD_BUDGET_KEYWORDS)
        for kw in group
        if kw in text
    })
    return {
        'platform_tags': platforms,
        'business_module': business[0] if business else '',
        'business_modules': business,
        'industry_module': industry[0] if industry else '',
        'industry_modules': industry,
        'matched_keywords': matched_keywords,
    }


def _lead_text_blob(lead: dict) -> str:
    parts = [
        lead.get('need'), lead.get('customer_need'), lead.get('evidence'), lead.get('intent'),
        lead.get('product_or_service'), lead.get('budget'), lead.get('urgency'),
    ]
    phones = lead.get('phones') if isinstance(lead.get('phones'), list) else []
    parts.extend(phones)
    return ' '.join(str(item or '') for item in parts).lower()


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _score_lead(lead: dict, phone: str = '') -> tuple[int, list[str]]:
    explicit = lead.get('lead_score') or lead.get('score')
    if explicit not in (None, ''):
        try:
            score = max(-100, min(150, int(float(explicit))))
            reasons = lead.get('score_reasons') if isinstance(lead.get('score_reasons'), list) else []
            return score, [str(item) for item in reasons if str(item or '').strip()]
        except Exception:
            pass

    text = _lead_text_blob(lead)
    score = 0
    reasons: list[str] = []

    if _contains_any(text, LEAD_NEED_KEYWORDS):
        score += 10
        reasons.append('Có từ khóa nhu cầu')
    if 'báo giá' in text or 'bao nhiêu' in text or 'giá' in text:
        score += 20
        reasons.append('Có yêu cầu báo giá/giá')
    if phone or extract_phones(text):
        score += 30
        reasons.append('Có số điện thoại')
    if _contains_any(text, LEAD_DEADLINE_KEYWORDS):
        score += 20
        reasons.append('Có deadline/thời điểm triển khai')
    if 'gấp' in text or 'ngay' in text:
        score += 25
        reasons.append('Có tín hiệu cần gấp')
    if _contains_any(text, LEAD_BUDGET_KEYWORDS):
        score += 25
        reasons.append('Có ngân sách/chi phí')
    if _contains_any(text, LEAD_SOLUTION_KEYWORDS):
        score += 30
        reasons.append('Khớp giải pháp F-Solution')
    if _contains_any(text, LEAD_POSITIVE_REPLY_KEYWORDS) and str(lead.get('source') or lead.get('lead_source') or '').lower() == 'comment':
        score += 40
        reasons.append('Khách phản hồi/comment xác nhận')

    confidence = lead.get('confidence')
    try:
        if float(confidence or 0) >= 0.9 and score > 0:
            score += 5
            reasons.append('AI/luật nhận diện độ chắc cao')
    except Exception:
        pass

    return max(0, min(150, score)), reasons


def _lead_level(score: int) -> tuple[str, str]:
    if score > 90:
        return 'very_hot', 'Lead rất nóng'
    if score >= 61:
        return 'hot', 'Lead nóng'
    if score >= 31:
        return 'warm', 'Lead ấm'
    if score >= 11:
        return 'interested', 'Lead quan tâm'
    return 'cold', 'Lead lạnh'


def _lead_sla_minutes(level: str) -> int:
    return {
        'interested': 24 * 60,
        'warm': 2 * 60,
        'hot': 30,
        'very_hot': 15,
    }.get(level, 0)


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        try:
            return parsedate_to_datetime(str(value))
        except Exception:
            return None


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _lead_due_at(created_at: str, level: str) -> str:
    minutes = _lead_sla_minutes(level)
    if not minutes:
        return ''
    base = _parse_dt(created_at) or datetime.now(timezone.utc)
    return _iso_utc(base.astimezone(timezone.utc) + timedelta(minutes=minutes))


def _lead_alert(level: str, status: str, due_at: str) -> tuple[str, str]:
    if status not in ('new', 'assigned', 'not_contacted', ''):
        return 'ok', 'Đã xử lý'
    if not due_at:
        return 'none', ''
    due = _parse_dt(due_at)
    if not due:
        return 'none', ''
    now = datetime.now(timezone.utc)
    remaining = (due.astimezone(timezone.utc) - now).total_seconds() / 60
    if remaining < 0:
        return 'red', 'Quá SLA'
    if level in ('hot', 'very_hot') and remaining <= 10:
        return 'red', 'Sắp quá SLA'
    if level == 'warm' and remaining <= 30:
        return 'orange', 'Sắp đến hạn'
    return 'ok', ''


def _lead_next_action(level: str, phone: str = '') -> str:
    if level == 'very_hot':
        return 'Gọi ngay, inbox, đặt lịch demo, gửi hồ sơ/case study và báo giá nhanh.'
    if level == 'hot':
        return 'Trong 30 phút: gọi điện/inbox, comment bài viết, đặt lịch demo và cập nhật CRM.'
    if level == 'warm':
        return 'Trong 2 giờ: inbox khách, comment bài viết, gọi nếu có SĐT, mục tiêu chuyển demo.'
    if level == 'interested':
        return 'Theo dõi, comment mềm, inbox nhẹ, gửi tài liệu hoặc demo mẫu.'
    return 'Chỉ lưu dữ liệu và theo dõi, chưa auto comment để tránh spam.'


# ── Điểm động theo hành vi khách (đặc tả Mục III) ──
BEHAVIOR_SCORE_RULES = {
    'comment_reply': (40, 'Khách comment phản hồi'),
    'inbox_reply': (50, 'Khách inbox phản hồi'),
    'agree_demo': (50, 'Khách đồng ý demo'),
    'detail_request': (30, 'Khách gửi yêu cầu chi tiết'),
    'provided_phone': (30, 'Khách cung cấp SĐT'),
    'no_reply_7d': (-20, 'Không phản hồi 7 ngày'),
    'rejected': (-50, 'Khách từ chối tư vấn'),
    'spam_fake': (-100, 'Spam/fake'),
}


def _behavior_score(lead: dict) -> tuple[int, list[str]]:
    """Tính tổng điểm cộng/trừ động dựa trên danh sách sự kiện hành vi đã ghi nhận."""
    events = lead.get('behavior_events')
    if not isinstance(events, list):
        return 0, []
    delta = 0
    reasons: list[str] = []
    seen: set[str] = set()
    for ev in events:
        ev_type = str((ev or {}).get('type') if isinstance(ev, dict) else ev or '').strip()
        if ev_type not in BEHAVIOR_SCORE_RULES:
            continue
        points, label = BEHAVIOR_SCORE_RULES[ev_type]
        delta += points
        if ev_type not in seen:
            sign = '+' if points >= 0 else ''
            reasons.append(f'{label} ({sign}{points})')
            seen.add(ev_type)
    return delta, reasons


def _normalise_lead(lead: dict, post_id: str = '') -> dict:
    if not isinstance(lead, dict):
        lead = {}
    phones = lead.get('phones') if isinstance(lead.get('phones'), list) else []
    phone = str(lead.get('phone') or lead.get('customer_phone') or (phones[0] if phones else '') or '').strip()
    if phone and phone not in phones:
        phones = [phone, *phones]
    phones = [str(item).strip() for item in phones if str(item or '').strip()]
    pid = str(lead.get('post_id') or post_id or '').strip()
    lead_source = str(lead.get('lead_source') or lead.get('source') or '').strip() or ('comment' if lead.get('comment_id') else 'post')
    platform = str(lead.get('platform') or lead.get('source_platform') or '').strip().lower()
    if not platform:
        platform = 'tiktok' if str(pid).startswith('tiktok_') else 'facebook'
    created_at = str(lead.get('created_at') or datetime.utcnow().isoformat(timespec='seconds') + 'Z')
    base_score, base_reasons = _score_lead(lead, phone)
    behavior_delta, behavior_reasons = _behavior_score(lead)
    score = max(-100, min(190, base_score + behavior_delta))
    reasons = base_reasons + behavior_reasons
    level, level_label = _lead_level(score)
    lead_status = str(lead.get('lead_status') or lead.get('crm_status') or 'new').strip() or 'new'
    sla_due_at = str(lead.get('sla_due_at') or _lead_due_at(created_at, level))
    alert_level, alert_label = _lead_alert(level, lead_status, sla_due_at)
    next_action = str(lead.get('next_action') or _lead_next_action(level, phone)).strip()
    modules = _classify_lead_modules({**lead, 'phone': phone, 'phones': phones})
    behavior_events = lead.get('behavior_events') if isinstance(lead.get('behavior_events'), list) else []
    status_history = lead.get('status_history') if isinstance(lead.get('status_history'), list) else []
    return {
        **lead,
        'lead_key': str(lead.get('lead_key') or _lead_key({**lead, 'post_id': pid, 'phone': phone})),
        'platform': platform,
        'post_id': pid,
        'group_id': str(lead.get('group_id') or '').strip(),
        'post_url': str(lead.get('post_url') or '').strip(),
        'comment_id': str(lead.get('comment_id') or lead.get('source_id') or '').strip(),
        'comment_url': str(lead.get('comment_url') or '').strip(),
        'source': lead_source,
        'source_id': str(lead.get('source_id') or lead.get('comment_id') or pid).strip(),
        'name': str(lead.get('name') or lead.get('customer_name') or 'Ẩn danh').strip(),
        'phone': phone,
        'phones': phones,
        'need': str(lead.get('need') or lead.get('customer_need') or lead.get('evidence') or '').strip(),
        'intent': str(lead.get('intent') or 'phone_comment').strip(),
        'product_or_service': str(lead.get('product_or_service') or '').strip(),
        'platform_tags': modules['platform_tags'],
        'business_module': modules['business_module'],
        'business_modules': modules['business_modules'],
        'industry_module': modules['industry_module'],
        'industry_modules': modules['industry_modules'],
        'matched_keywords': modules['matched_keywords'],
        'location': str(lead.get('location') or '').strip(),
        'budget': str(lead.get('budget') or '').strip(),
        'urgency': str(lead.get('urgency') or 'medium').strip(),
        'contact_status': 'has_phone' if phone else str(lead.get('contact_status') or 'no_phone'),
        'confidence': float(lead.get('confidence') or (0.95 if phone else 0.6)),
        'evidence': str(lead.get('evidence') or '').strip(),
        'lead_score': score,
        'score_reasons': reasons,
        'lead_level': level,
        'lead_level_label': level_label,
        'lead_status': lead_status,
        'assigned_sale_id': str(lead.get('assigned_sale_id') or '').strip(),
        'assigned_sale_name': str(lead.get('assigned_sale_name') or lead.get('assigned_sale') or '').strip(),
        'sla_minutes': _lead_sla_minutes(level),
        'sla_due_at': sla_due_at,
        'alert_level': alert_level,
        'alert_label': alert_label,
        'next_action': next_action,
        'behavior_events': behavior_events,
        'status_history': status_history,
        'created_at': created_at,
    }


def _merge_leads_into_memory(leads: list[dict]) -> int:
    global _leads
    changed = 0
    for lead in leads or []:
        row = _normalise_lead(lead)
        pid = row.get('post_id')
        if not pid:
            continue
        bucket = _leads.setdefault(pid, [])
        existing = {str(item.get('lead_key') or _lead_key(item)): idx for idx, item in enumerate(bucket)}
        key = str(row.get('lead_key'))
        public_row = {k: v for k, v in row.items() if k != 'raw_lead'}
        if key in existing:
            bucket[existing[key]] = {**bucket[existing[key]], **public_row}
        else:
            bucket.append(public_row)
            changed += 1
    if changed:
        _save_leads()
    return changed


def _lead_to_supabase_row(lead: dict) -> dict:
    row = _normalise_lead(lead)
    staff = _current_staff()
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    return {
        'lead_key': row.get('lead_key'),
        'platform': row.get('platform'),
        'lead_source': row.get('source'),
        'source_id': row.get('source_id'),
        'post_id': row.get('post_id'),
        'group_id': row.get('group_id'),
        'post_url': row.get('post_url'),
        'comment_id': row.get('comment_id'),
        'comment_url': row.get('comment_url'),
        'customer_name': row.get('name'),
        'customer_phone': row.get('phone'),
        'phones': row.get('phones') or [],
        'customer_need': row.get('need'),
        'intent': row.get('intent'),
        'product_or_service': row.get('product_or_service'),
        'location': row.get('location'),
        'budget': row.get('budget'),
        'urgency': row.get('urgency'),
        'contact_status': row.get('contact_status'),
        'confidence': row.get('confidence'),
        'evidence': row.get('evidence'),
        'lead_score': row.get('lead_score') or 0,
        'score_reasons': row.get('score_reasons') or [],
        'lead_level': row.get('lead_level') or 'cold',
        'lead_status': row.get('lead_status') or 'new',
        'assigned_sale_id': row.get('assigned_sale_id') or '',
        'assigned_sale_name': row.get('assigned_sale_name') or '',
        'sla_minutes': row.get('sla_minutes') or 0,
        'sla_due_at': row.get('sla_due_at') or None,
        'alert_level': row.get('alert_level') or '',
        'next_action': row.get('next_action') or '',
        'platform_tags': row.get('platform_tags') or [],
        'business_module': row.get('business_module') or '',
        'industry_module': row.get('industry_module') or '',
        'matched_keywords': row.get('matched_keywords') or [],
        'behavior_events': row.get('behavior_events') or [],
        'status_history': row.get('status_history') or [],
        'raw_lead': row,
        'created_by_staff_id': staff.get('id', ''),
        'created_by_staff_name': staff.get('name', ''),
        'created_by_staff_username': staff.get('username', ''),
        'created_at': row.get('created_at') or now,
        'updated_at': now,
    }


def _save_leads_to_supabase(leads: list[dict]) -> tuple[bool, str]:
    if not leads:
        return True, ''
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, 'Chưa cấu hình Supabase'
    rows_by_key = {}
    for lead in leads:
        row = _lead_to_supabase_row(lead)
        if row.get('lead_key'):
            rows_by_key[row['lead_key']] = row
    rows = list(rows_by_key.values())
    if not rows:
        return True, ''
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates,return=minimal',
    }
    crm_columns = {
        'lead_score', 'score_reasons', 'lead_level', 'lead_status',
        'assigned_sale_id', 'assigned_sale_name', 'sla_minutes', 'sla_due_at',
        'alert_level', 'next_action',
        'platform_tags', 'business_module', 'industry_module', 'matched_keywords',
        'behavior_events', 'status_history',
    }

    def post_chunk(chunk: list[dict]):
        return _req.post(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_LEAD_TABLE}?on_conflict=lead_key",
            headers=headers,
            json=chunk,
            timeout=30,
        )

    def schema_column_error(resp) -> bool:
        text = (resp.text or '').lower()
        return 'schema cache' in text and 'column' in text

    try:
        for i in range(0, len(rows), 200):
            chunk = rows[i:i + 200]
            resp = post_chunk(chunk)
            if resp.status_code not in (200, 201, 204) and schema_column_error(resp):
                fallback = [{k: v for k, v in row.items() if k not in crm_columns} for row in chunk]
                resp = post_chunk(fallback)
            if resp.status_code not in (200, 201, 204):
                if resp.headers.get('content-type', '').startswith('application/json'):
                    try:
                        return False, (resp.json().get('message') or resp.text)[:300]
                    except Exception:
                        pass
                return False, resp.text[:300]
        return True, ''
    except Exception as e:
        return False, str(e)[:300]


def _supabase_lead_row_to_public(row: dict) -> dict:
    raw = row.get('raw_lead') if isinstance(row.get('raw_lead'), dict) else {}
    return {
        **raw,
        'id': row.get('id'),
        'lead_key': row.get('lead_key'),
        'platform': row.get('platform') or raw.get('platform') or '',
        'source': row.get('lead_source') or raw.get('source') or '',
        'source_id': row.get('source_id') or raw.get('source_id') or '',
        'post_id': row.get('post_id') or raw.get('post_id') or '',
        'group_id': row.get('group_id') or raw.get('group_id') or '',
        'post_url': row.get('post_url') or raw.get('post_url') or '',
        'comment_id': row.get('comment_id') or raw.get('comment_id') or '',
        'comment_url': row.get('comment_url') or raw.get('comment_url') or '',
        'name': row.get('customer_name') or raw.get('name') or 'Ẩn danh',
        'phone': row.get('customer_phone') or raw.get('phone') or '',
        'phones': row.get('phones') or raw.get('phones') or [],
        'need': row.get('customer_need') or raw.get('need') or '',
        'intent': row.get('intent') or raw.get('intent') or '',
        'product_or_service': row.get('product_or_service') or raw.get('product_or_service') or '',
        'location': row.get('location') or raw.get('location') or '',
        'budget': row.get('budget') or raw.get('budget') or '',
        'urgency': row.get('urgency') or raw.get('urgency') or '',
        'contact_status': row.get('contact_status') or raw.get('contact_status') or '',
        'confidence': row.get('confidence') or raw.get('confidence') or 0,
        'evidence': row.get('evidence') or raw.get('evidence') or '',
        'lead_score': row.get('lead_score') or raw.get('lead_score') or raw.get('score') or 0,
        'score_reasons': row.get('score_reasons') or raw.get('score_reasons') or [],
        'lead_level': row.get('lead_level') or raw.get('lead_level') or '',
        'lead_level_label': raw.get('lead_level_label') or '',
        'lead_status': row.get('lead_status') or raw.get('lead_status') or raw.get('crm_status') or 'new',
        'assigned_sale_id': row.get('assigned_sale_id') or raw.get('assigned_sale_id') or '',
        'assigned_sale_name': row.get('assigned_sale_name') or raw.get('assigned_sale_name') or raw.get('assigned_sale') or '',
        'sla_minutes': row.get('sla_minutes') or raw.get('sla_minutes') or 0,
        'sla_due_at': row.get('sla_due_at') or raw.get('sla_due_at') or '',
        'alert_level': row.get('alert_level') or raw.get('alert_level') or '',
        'alert_label': raw.get('alert_label') or '',
        'next_action': row.get('next_action') or raw.get('next_action') or '',
        'created_at': row.get('created_at') or raw.get('created_at') or '',
        'updated_at': row.get('updated_at') or raw.get('updated_at') or '',
    }


def _load_leads_from_supabase(limit: int = 3000) -> tuple[dict, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}, 'Chưa cấu hình Supabase'
    try:
        resp = _req.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_LEAD_TABLE}",
            headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
            params={
                'select': '*',
                'order': 'created_at.desc',
                'limit': str(max(1, min(int(limit or 3000), 5000))),
            },
            timeout=30,
        )
        if resp.status_code not in (200, 206):
            return {}, resp.text[:300]
        grouped: dict[str, list] = {}
        for row in resp.json() or []:
            lead = _normalise_lead(_supabase_lead_row_to_public(row))
            pid = str(lead.get('post_id') or '')
            if pid:
                grouped.setdefault(pid, []).append(lead)
        return grouped, ''
    except Exception as e:
        return {}, str(e)[:300]


def _flatten_lead_groups(grouped: dict) -> list[dict]:
    rows: list[dict] = []
    for post_id, items in (grouped or {}).items():
        for item in items or []:
            rows.append(_normalise_lead({**item, 'post_id': item.get('post_id') or post_id}, str(post_id)))
    return rows


# ── Chia lead cho Sale (đặc tả Bước 6/7) ──
_assign_lock = threading.Lock()
_assign_cursor = 0


def _sale_roster() -> list[dict]:
    """Danh sách nhân sự sale đủ điều kiện nhận lead (đang bật)."""
    roster = []
    for item in _staff_accounts():
        if not item.get('enabled', True):
            continue
        roster.append({
            'id': str(item.get('id') or ''),
            'name': str(item.get('name') or item.get('username') or 'Sale'),
            'role': str(item.get('role') or 'staff'),
        })
    return roster


def _auto_assign_sale(lead: dict) -> dict:
    """Tự động chia lead cho sale theo round-robin nếu chưa có sale phụ trách."""
    if str(lead.get('assigned_sale_id') or '').strip() or str(lead.get('assigned_sale_name') or '').strip():
        return lead
    roster = _sale_roster()
    if not roster:
        return lead
    global _assign_cursor
    with _assign_lock:
        sale = roster[_assign_cursor % len(roster)]
        _assign_cursor += 1
    lead['assigned_sale_id'] = sale['id']
    lead['assigned_sale_name'] = sale['name']
    return lead


def _pick_other_sale(current_sale_id: str) -> dict:
    """Chọn một sale khác sale hiện tại để escalation."""
    roster = _sale_roster()
    others = [s for s in roster if s['id'] != str(current_sale_id or '')]
    pool = others or roster
    if not pool:
        return {}
    global _assign_cursor
    with _assign_lock:
        sale = pool[_assign_cursor % len(pool)]
        _assign_cursor += 1
    return sale


def _append_status_history(lead: dict, status: str, note: str = '', by: str = '') -> list:
    """Ghi timeline thay đổi trạng thái lead (đặc tả Bước 7)."""
    history = lead.get('status_history') if isinstance(lead.get('status_history'), list) else []
    if history and history[-1].get('status') == status and not note:
        return history
    history = [*history, {
        'status': status,
        'note': note,
        'by': by,
        'at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
    }]
    lead['status_history'] = history
    return history


def _postprocess_new_leads(leads: list[dict], posts_by_id: dict | None = None) -> list[dict]:
    """Áp dụng chia sale tự động + thông báo lead nóng + auto-comment cho lead vừa tạo (đặc tả Bước 6/7/4)."""
    auto_assign = _settings.get('auto_assign_sale', True)
    notify_hot = _settings.get('notify_hot_lead', True)
    auto_comment = _settings.get('auto_comment_hot', False)
    posts_by_id = posts_by_id or {}
    processed: list[dict] = []
    for lead in leads or []:
        if not isinstance(lead, dict):
            continue
        if auto_assign:
            _auto_assign_sale(lead)
            # gắn trạng thái khởi tạo vào timeline nếu chưa có
            if not lead.get('status_history'):
                _append_status_history(lead, str(lead.get('lead_status') or 'new'), note='Lead được tạo', by='system')
        normalised = _normalise_lead(lead, lead.get('post_id') or '')
        processed.append(normalised)
        if notify_hot and normalised.get('lead_level') in ('hot', 'very_hot'):
            threading.Thread(target=_notify_hot_lead, args=(normalised,), daemon=True).start()
        if auto_comment and normalised.get('lead_level') in ('hot', 'very_hot'):
            post = posts_by_id.get(str(normalised.get('post_id') or ''))
            threading.Thread(target=_auto_comment_lead, args=(normalised, post), daemon=True).start()
    return processed


# ── Bot auto-comment cho lead nóng (đặc tả Bước 4) ──
# Thiết kế an toàn: chỉ chạy khi bật thủ công, chỉ lead nóng/rất nóng,
# có giới hạn số comment/giờ để giảm rủi ro khóa tài khoản Facebook.
_auto_comment_lock = threading.Lock()
_auto_comment_times: list = []   # epoch các lần auto comment gần đây
_auto_commented_keys: set = set()  # lead_key đã auto comment để tránh trùng


def _auto_comment_quota_ok() -> bool:
    limit = int(_settings.get('auto_comment_max_per_hour', 8) or 8)
    now = _time.time()
    with _auto_comment_lock:
        cutoff = now - 3600
        _auto_comment_times[:] = [t for t in _auto_comment_times if t >= cutoff]
        return len(_auto_comment_times) < limit


def _auto_comment_record_time():
    with _auto_comment_lock:
        _auto_comment_times.append(_time.time())


def _build_auto_comment_message(lead: dict, post: dict | None = None) -> str:
    """Tạo nội dung comment: ưu tiên gợi ý AI nếu có ngữ cảnh bài, nếu không dùng mẫu từ hồ sơ bán hàng."""
    phone = str((_business_profile or {}).get('phone') or '').strip()
    if post:
        try:
            classifier = _get_classifier()
            if classifier.api_key:
                suggestion = classifier.suggest_reply(post, '', _business_profile)
                replies = suggestion.get('suggested_replies') or []
                if phone:
                    for r in replies:
                        if phone in str(r.get('text') or ''):
                            return str(r.get('text') or '').strip()
                for r in replies:
                    label = str(r.get('label') or '').lower()
                    if 'chốt' in label or 'inbox' in label:
                        return str(r.get('text') or '').strip()
                if replies:
                    return str(replies[0].get('text') or '').strip()
        except Exception:
            pass
    # Mẫu dự phòng khi không có ngữ cảnh/AI
    biz = str((_business_profile or {}).get('business_name') or 'F-Solution').strip()
    need = str(lead.get('need') or '').strip()
    name = str(lead.get('name') or '').strip()
    greeting = f'Chào anh/chị {name}, ' if name and name != 'Ẩn danh' else 'Chào anh/chị, '
    body = f'{biz} có thể hỗ trợ {need} ạ. ' if need else f'{biz} có thể hỗ trợ nhu cầu của anh/chị ạ. '
    cta = 'Anh/chị inbox giúp em để được tư vấn nhanh nhé.'
    if phone:
        cta += f' Hoặc liên hệ {phone}.'
    return (greeting + body + cta).strip()


def _auto_comment_lead(lead: dict, post: dict | None = None, force: bool = False) -> tuple[bool, str]:
    """Đăng comment tự động cho 1 lead nóng/rất nóng. Trả về (ok, comment_id|error)."""
    level = str(lead.get('lead_level') or '')
    if not force and level not in ('hot', 'very_hot'):
        return False, 'Chỉ auto comment với lead nóng/rất nóng'
    if str(lead.get('platform') or 'facebook') != 'facebook':
        return False, 'Hiện chỉ hỗ trợ auto comment trên Facebook'
    post_id = str(lead.get('post_id') or '')
    if not post_id:
        return False, 'Lead thiếu post_id để comment'
    key = str(lead.get('lead_key') or '')
    if key and key in _auto_commented_keys and not force:
        return False, 'Lead này đã được auto comment'
    if not _auto_comment_quota_ok():
        return False, 'Đã đạt giới hạn auto comment trong 1 giờ'
    message = _build_auto_comment_message(lead, post)
    if not message:
        return False, 'Chưa tạo được nội dung comment'
    group_id = str(lead.get('group_id') or DEFAULT_GROUP)
    post_url = str(lead.get('post_url') or '')
    try:
        result = get_api(group_id).post_comment(post_id, message)
    except Exception as e:
        _record_comment_log(post_id, group_id, post_url, message, '', 'failed', error_message=str(e))
        return False, str(e)
    if result and 'id' in result:
        _record_comment_log(post_id, group_id, post_url, message, '', 'success', comment_id=result['id'])
        _auto_comment_record_time()
        if key:
            _auto_commented_keys.add(key)
            # ghi vào timeline + đánh dấu đã liên hệ tự động
            _append_status_history(lead, str(lead.get('lead_status') or 'new'), note=f'Bot auto comment: {message[:80]}', by='bot')
            _update_lead_in_memory(key, {'status_history': lead.get('status_history')})
        return True, result['id']
    err = (result or {}).get('error', {}).get('message', 'Lỗi không xác định')
    _record_comment_log(post_id, group_id, post_url, message, '', 'failed', error_message=err)
    return False, err


def _lead_dashboard_payload(grouped: dict) -> dict:
    rows = _flatten_lead_groups(grouped)
    total = len(rows)
    by_level = {key: 0 for key in ['cold', 'interested', 'warm', 'hot', 'very_hot']}
    by_status: dict[str, int] = {}
    by_group: dict[str, int] = {}
    by_platform: dict[str, int] = {}
    by_sale: dict[str, int] = {}
    by_industry: dict[str, int] = {}
    overdue = 0
    hot = 0
    very_hot = 0
    new_count = 0
    contacted = 0
    responded = 0
    demo = 0
    quoted = 0
    won = 0
    lost = 0
    spam = 0
    auto_comment_candidates = 0
    scores: list[int] = []

    for lead in rows:
        level = str(lead.get('lead_level') or 'cold')
        status = str(lead.get('lead_status') or 'new')
        platform = str(lead.get('platform') or 'unknown')
        group_id = str(lead.get('group_id') or 'unknown')
        sale_name = str(lead.get('assigned_sale_name') or '').strip() or 'Chưa chia'
        industry = str(lead.get('industry_module') or '').strip() or 'Khác'
        score = int(lead.get('lead_score') or 0)
        scores.append(score)
        by_level[level] = by_level.get(level, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_group[group_id] = by_group.get(group_id, 0) + 1
        by_platform[platform] = by_platform.get(platform, 0) + 1
        by_sale[sale_name] = by_sale.get(sale_name, 0) + 1
        by_industry[industry] = by_industry.get(industry, 0) + 1
        if level in ('hot', 'very_hot'):
            hot += 1
        if level == 'very_hot':
            very_hot += 1
        if str(lead.get('alert_level') or '') in ('red', 'orange'):
            overdue += 1
        if status == 'new':
            new_count += 1
        if status in ('contacted', 'consulting', 'demo', 'quoted', 'won', 'lost'):
            contacted += 1
        if status in ('consulting', 'demo', 'quoted', 'won'):
            responded += 1
        if status == 'demo':
            demo += 1
        if status == 'quoted':
            quoted += 1
        if status == 'won':
            won += 1
        if status == 'lost':
            lost += 1
        if score <= -50 or 'spam' in ' '.join(str(r).lower() for r in (lead.get('score_reasons') or [])):
            spam += 1
        if level in ('hot', 'very_hot'):
            auto_comment_candidates += 1

    def pct_value(num: int, denom: int = total) -> float:
        return round((num / denom) * 100, 1) if denom else 0

    return {
        'total': total,
        'new_count': new_count,
        'hot_count': hot,
        'very_hot_count': very_hot,
        'overdue_count': overdue,
        'spam_count': spam,
        'won_count': won,
        'lost_count': lost,
        'scanned_today': _count_scanned_today(),
        'avg_score': round(sum(scores) / len(scores), 1) if scores else 0,
        'by_level': by_level,
        'by_status': by_status,
        'by_platform': by_platform,
        'by_sale': by_sale,
        'by_industry': by_industry,
        'top_groups': sorted(
            [{'group_id': key, 'count': value} for key, value in by_group.items()],
            key=lambda item: item['count'],
            reverse=True,
        )[:8],
        'rates': {
            'hot_rate': pct_value(hot),
            'contacted_rate': pct_value(contacted),
            'response_rate': pct_value(responded),
            'demo_rate': pct_value(demo),
            'quoted_rate': pct_value(quoted),
            'won_rate': pct_value(won),
            'spam_rate': pct_value(spam),
            'auto_comment_candidate_rate': pct_value(auto_comment_candidates),
        },
    }


def _update_lead_in_memory(lead_key: str, patch: dict) -> tuple[bool, dict]:
    global _leads
    for post_id, items in (_leads or {}).items():
        for idx, item in enumerate(items or []):
            key = str(item.get('lead_key') or _lead_key(item))
            if key == lead_key:
                next_row = _normalise_lead({**item, **patch, 'lead_key': lead_key, 'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z'}, str(post_id))
                _leads[post_id][idx] = next_row
                _save_leads()
                return True, next_row
    return False, {}


def _patch_lead_in_supabase(lead_key: str, row: dict) -> tuple[bool, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, 'Chưa cấu hình Supabase'
    payload = {
        'contact_status': row.get('contact_status'),
        'confidence': row.get('confidence'),
        'lead_score': row.get('lead_score') or 0,
        'score_reasons': row.get('score_reasons') or [],
        'lead_level': row.get('lead_level') or 'cold',
        'lead_status': row.get('lead_status') or 'new',
        'assigned_sale_id': row.get('assigned_sale_id') or '',
        'assigned_sale_name': row.get('assigned_sale_name') or '',
        'sla_minutes': row.get('sla_minutes') or 0,
        'sla_due_at': row.get('sla_due_at') or None,
        'alert_level': row.get('alert_level') or '',
        'next_action': row.get('next_action') or '',
        'platform_tags': row.get('platform_tags') or [],
        'business_module': row.get('business_module') or '',
        'industry_module': row.get('industry_module') or '',
        'matched_keywords': row.get('matched_keywords') or [],
        'behavior_events': row.get('behavior_events') or [],
        'status_history': row.get('status_history') or [],
        'raw_lead': row,
        'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
    }
    try:
        resp = _req.patch(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_LEAD_TABLE}",
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal',
            },
            params={'lead_key': f'eq.{lead_key}'},
            json=payload,
            timeout=30,
        )
        if resp.status_code not in (200, 204):
            if 'schema cache' in (resp.text or '').lower() and 'column' in (resp.text or '').lower():
                minimal_payload = {
                    'contact_status': row.get('contact_status'),
                    'confidence': row.get('confidence'),
                    'raw_lead': row,
                    'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
                }
                resp = _req.patch(
                    f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_LEAD_TABLE}",
                    headers={
                        'apikey': SUPABASE_KEY,
                        'Authorization': f'Bearer {SUPABASE_KEY}',
                        'Content-Type': 'application/json',
                        'Prefer': 'return=minimal',
                    },
                    params={'lead_key': f'eq.{lead_key}'},
                    json=minimal_payload,
                    timeout=30,
                )
                if resp.status_code in (200, 204):
                    return True, ''
            return False, resp.text[:300]
        return True, ''
    except Exception as e:
        return False, str(e)[:300]


def _comment_rows_to_phone_leads(rows: list[dict]) -> list[dict]:
    leads: list[dict] = []
    for row in rows or []:
        message = str(row.get('message') or '').strip()
        phones = extract_phones(message)
        if not phones:
            continue
        public = _public_comment_row(row)
        post_id = str(row.get('post_id') or '')
        platform = str(row.get('source') or '').lower() or ('tiktok' if post_id.startswith('tiktok_') else 'facebook')
        leads.append(_normalise_lead({
            'platform': platform,
            'source': 'comment',
            'source_id': row.get('comment_id') or '',
            'comment_id': row.get('comment_id') or '',
            'post_id': post_id,
            'group_id': row.get('group_id') or '',
            'post_url': row.get('post_url') or '',
            'comment_url': public.get('comment_url') or row.get('post_url') or '',
            'name': row.get('author_name') or 'Ẩn danh',
            'phone': phones[0],
            'phones': phones,
            'need': message[:220],
            'intent': 'phone_comment',
            'contact_status': 'has_phone',
            'confidence': 0.95,
            'evidence': message[:300],
        }))
    return leads


def _sync_phone_leads_from_comment_rows(rows: list[dict]) -> tuple[int, str]:
    leads = _comment_rows_to_phone_leads(rows)
    if not leads:
        return 0, ''
    changed = _merge_leads_into_memory(leads)
    ok, error = _save_leads_to_supabase(leads)
    return changed, '' if ok else error


def _save_reply_suggestions():
    _write_json(REPLY_SUGGESTIONS_FILE, _reply_suggestions)


def _save_staff_cookies():
    _write_json(STAFF_COOKIES_FILE, _staff_cookies)


def _save_comment_logs():
    _write_json(COMMENT_LOGS_FILE, _comment_logs[-1000:])


def _save_comment_summaries():
    _write_json(COMMENT_SUMMARIES_FILE, _comment_summaries)


def _save_post_comments():
    _write_json(POST_COMMENTS_FILE, _post_comments[-5000:])


def _save_managed_channels():
    _write_json(MANAGED_CHANNELS_FILE, _managed_channels)


def _extract_cookie_user(cookie: str) -> str:
    match = re.search(r'(?:^|;\s*)c_user=([^;]+)', cookie or '')
    return match.group(1) if match else ''


def _extract_cookie_value(cookie: str, name: str) -> str:
    match = re.search(rf'(?:^|;\s*){re.escape(name)}=([^;]+)', cookie or '')
    return match.group(1) if match else ''


def _mask_cookie(cookie: str) -> str:
    if not cookie:
        return ''
    c_user = _extract_cookie_user(cookie)
    if c_user:
        return f'c_user={c_user}; ...'
    return cookie[:8] + '...' + cookie[-6:] if len(cookie) > 18 else '***'


def _mask_tiktok_cookie(cookie: str) -> str:
    if not cookie:
        return ''
    for key in ('sessionid', 'sid_tt', 'tt_csrf_token', 'msToken'):
        value = _extract_cookie_value(cookie, key)
        if value:
            return f'{key}={value[:6]}...{value[-4:]}' if len(value) > 12 else f'{key}=***'
    return cookie[:10] + '...' + cookie[-6:] if len(cookie) > 20 else '***'


TIKTOK_LOGIN_COOKIE_KEYS = ('sessionid', 'sessionid_ss', 'sid_tt', 'sid_guard', 'uid_tt', 'uid_tt_ss')


def _has_tiktok_login_cookie(cookie: str) -> bool:
    return any(_extract_cookie_value(cookie, key) for key in TIKTOK_LOGIN_COOKIE_KEYS)


def _tiktok_cookie_login_message(cookie: str) -> str:
    if not cookie:
        return 'Chưa có TikTok cookie.'
    if _has_tiktok_login_cookie(cookie):
        return 'Cookie có session đăng nhập TikTok. Nếu vẫn lỗi, phiên đăng nhập đã hết hạn hoặc TikTok chặn thao tác.'
    return 'Cookie TikTok thiếu session đăng nhập như sessionid/sid_tt. Hãy đăng nhập TikTok rồi copy cookie đầy đủ từ tiktok.com.'


def _friendly_tiktok_publish_error(message: str) -> str:
    text = str(message or '').strip()
    lower = text.lower()
    if any(token in lower for token in ('đăng nhập', 'login', 'expired', 'session', 'hết hạn')):
        return 'Cookie TikTok đã hết hạn hoặc chưa phải cookie của tài khoản đang đăng nhập. Mở tiktok.com, đăng nhập lại rồi copy cookie đầy đủ vào menu Cooki.'
    return text or 'TikTok không nhận bình luận'


def _configured_tiktok_cookie() -> str:
    return str((_tiktok_config or {}).get('cookie') or TIKTOK_COOKIE or '').strip()


def _public_tiktok_config() -> dict:
    cookie = _configured_tiktok_cookie()
    source = 'web' if str((_tiktok_config or {}).get('cookie') or '').strip() else ('env' if TIKTOK_COOKIE else '')
    return {
        'has_cookie': bool(cookie),
        'has_login_cookie': _has_tiktok_login_cookie(cookie),
        'cookie_masked': _mask_tiktok_cookie(cookie),
        'source': source,
        'updated_at': (_tiktok_config or {}).get('updated_at') or '',
        'updated_by': (_tiktok_config or {}).get('updated_by') or '',
        'can_manage': _is_admin(),
    }


def _public_staff_cookie(row: dict) -> dict:
    cookie = row.get('cookie', '')
    return {
        'id': row.get('id', ''),
        'name': row.get('name', ''),
        'username': row.get('username', ''),
        'role': row.get('role', 'staff'),
        'cookie_masked': _mask_cookie(cookie),
        'facebook_user_id': row.get('facebook_user_id') or _extract_cookie_user(cookie),
        'enabled': bool(row.get('enabled', True)),
        'created_at': row.get('created_at', ''),
        'updated_at': row.get('updated_at', ''),
    }


def _staff_accounts() -> list:
    return _staff_cookies.get('staff') or []


def _as_enabled(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ('0', 'false', 'no', 'off', 'disabled')
    return bool(value)


def _normalize_supabase_staff(row: dict) -> dict:
    username = str(row.get('username') or row.get('account') or row.get('login') or '').strip().lower()
    name = str(row.get('name') or row.get('staff_name') or username or 'Nhân sự').strip()
    cookie = str(row.get('cookie') or row.get('facebook_cookie') or row.get('fb_cookie') or '').strip()
    role = str(row.get('role') or '').strip().lower()
    if not role:
        role = 'admin' if row.get('is_admin') is True else 'staff'
    return {
        'id': str(row.get('id') or username or uuid.uuid4().hex[:12]),
        'name': name,
        'username': username,
        'cookie': cookie,
        'role': role,
        'enabled': _as_enabled(row.get('enabled', True)),
        'facebook_user_id': str(row.get('facebook_user_id') or _extract_cookie_user(cookie) or ''),
        'created_at': row.get('created_at', ''),
        'updated_at': row.get('updated_at', ''),
        '_auth_source': 'supabase',
    }


def _plain_password_from_row(row: dict) -> str:
    for key in ('password', 'pass', 'plain_password', 'mat_khau'):
        value = row.get(key)
        if value is not None:
            return str(value)
    return ''


def _supabase_password_matches(row: dict, password: str) -> bool:
    digest = row.get('password_hash') or row.get('pass_hash')
    salt = row.get('password_salt') or row.get('salt')
    if digest and salt and _verify_password(password, str(salt), str(digest)):
        return True
    plain = _plain_password_from_row(row)
    return bool(plain) and secrets.compare_digest(plain, password)


def _find_local_staff(username: str) -> dict:
    username = (username or '').strip().lower()
    return next((item for item in _staff_accounts()
                 if item.get('enabled', True) and item.get('username') == username), {})


def _load_supabase_staff(username: str) -> tuple[dict, str]:
    if not USE_SUPABASE:
        return {}, ''
    try:
        row = sb.get_staff_user(username, SUPABASE_STAFF_TABLE)
        return row or {}, ''
    except Exception as e:
        return {}, str(e)


def _list_supabase_staff() -> tuple[list, str]:
    if not USE_SUPABASE:
        return [], ''
    try:
        return [_normalize_supabase_staff(row) for row in sb.list_staff_users(SUPABASE_STAFF_TABLE)], ''
    except Exception as e:
        return [], str(e)


def _merged_public_staff_rows() -> tuple[list, str]:
    merged: dict[str, dict] = {}
    for item in _staff_accounts():
        if not _as_enabled(item.get('enabled', True)):
            continue
        key = item.get('id') or item.get('username')
        if key:
            merged[key] = item

    remote_rows, warning = _list_supabase_staff()
    for item in remote_rows:
        if not _as_enabled(item.get('enabled', True)):
            continue
        key = item.get('id') or item.get('username')
        if key:
            merged[key] = item

    current = _current_staff()
    if current:
        merged[current.get('id') or current.get('username') or 'current'] = current
    return [_public_staff_cookie(item) for item in merged.values() if item], warning


def _set_logged_in_staff(staff: dict) -> None:
    old_token = session.pop('staff_cache_token', None)
    if old_token:
        _session_staff_cache.pop(old_token, None)

    session['staff_id'] = staff.get('id', '')
    session['staff_username'] = staff.get('username', '')
    session['staff_source'] = staff.get('_auth_source', 'local')

    if staff.get('_auth_source') == 'supabase':
        token = uuid.uuid4().hex
        _session_staff_cache[token] = staff
        session['staff_cache_token'] = token


def _clear_logged_in_staff() -> None:
    token = session.pop('staff_cache_token', None)
    if token:
        _session_staff_cache.pop(token, None)
    session.pop('staff_id', None)
    session.pop('staff_username', None)
    session.pop('staff_source', None)


def _setup_required() -> bool:
    if SIMPLE_LOGIN_ONLY:
        return False
    return not any(item.get('enabled', True) and item.get('username') and item.get('password_hash') for item in _staff_accounts())


def _current_staff() -> dict:
    staff_id = session.get('staff_id', '')
    if not staff_id:
        return {}
    local = next((item for item in _staff_accounts() if item.get('id') == staff_id and item.get('enabled', True)), {})
    if local:
        return local

    token = session.get('staff_cache_token', '')
    cached = _session_staff_cache.get(token) if token else None
    if cached and cached.get('id') == staff_id and cached.get('enabled', True):
        return cached

    if session.get('staff_source') == 'supabase':
        row, _ = _load_supabase_staff(session.get('staff_username', ''))
        if row:
            staff = _normalize_supabase_staff(row)
            if staff.get('id') == staff_id and staff.get('enabled', True):
                token = uuid.uuid4().hex
                _session_staff_cache[token] = staff
                session['staff_cache_token'] = token
                return staff
    return {}


def _current_staff_id() -> str:
    return _current_staff().get('id', '')


def _is_admin() -> bool:
    return str(_current_staff().get('role') or '').strip().lower() == 'admin'


def _public_current_staff() -> dict:
    staff = _current_staff()
    return _public_staff_cookie(staff) if staff else {}


def _active_staff() -> dict:
    current = _current_staff()
    if current:
        return current
    if _setup_required():
        return {}
    active_id = _staff_cookies.get('active_staff_id', '')
    active = next((item for item in _staff_accounts() if item.get('id') == active_id and item.get('enabled', True)), None)
    return active or {}


def _active_staff_id() -> str:
    return _active_staff().get('id', '')


def _active_cookie() -> str:
    return _active_staff().get('cookie', '')


def _staff_token_file(staff_id: str) -> str:
    safe_id = re.sub(r'[^a-zA-Z0-9_-]+', '_', staff_id or 'default')
    return os.path.join(STAFF_TOKEN_DIR, f'{safe_id}.txt')


def _invalidate_facebook_cache():
    _api_cache.clear()
    _pages_cache.clear()


def _remove_staff_token_file(staff_id: str) -> None:
    try:
        os.remove(_staff_token_file(staff_id))
    except OSError:
        pass


def _refresh_staff_session_cache(staff_id: str, staff_row: dict) -> None:
    """Nếu đang sửa chính tài khoản đăng nhập, cập nhật ngay cookie trong session cache."""
    if not staff_id or session.get('staff_id') != staff_id:
        return
    token = session.get('staff_cache_token', '')
    if token:
        _session_staff_cache[token] = {**staff_row, '_auth_source': session.get('staff_source', 'local') or 'local'}


def _clean_business_profile(body: dict) -> dict:
    current = {**_default_business_profile(), **(_business_profile or {})}
    limits = {
        'business_name': 120,
        'phone': 60,
        'address': 240,
        'why_choose_us': 1000,
        'extra_notes': 800,
    }
    for key, limit in limits.items():
        if key in body:
            current[key] = str(body.get(key) or '').strip()[:limit]
    return current


def _extract_target_id_from_link(link: str) -> str:
    link = (link or '').strip()
    if not link:
        return ''
    patterns = (
        r'(?:/video/|/videos/)([A-Za-z0-9_.-]+)',
        r'/groups/([A-Za-z0-9_.-]+)',
        r'[?&]id=([A-Za-z0-9_.-]+)',
        r'/channel/([A-Za-z0-9_.-]+)',
        r'@([A-Za-z0-9_.-]+)',
    )
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1).strip('/')
    nums = re.findall(r'\d{6,}', link)
    return nums[-1] if nums else ''


def _is_valid_facebook_numeric_id(value: str) -> bool:
    return bool(re.fullmatch(r'\d{10,20}', str(value or '').strip()))


def _facebook_channel_validation_error(row: dict) -> str:
    platform = str(row.get('platform') or '').strip().lower()
    channel_type = str(row.get('channel_type') or '').strip().lower()
    target_id = str(row.get('target_id') or '').strip()
    if platform != 'facebook':
        return ''
    if channel_type in ('nhóm', 'nhom', 'group', 'page', 'fanpage') and target_id and not _is_valid_facebook_numeric_id(target_id):
        return 'ID Facebook chưa hợp lệ. Hãy nhập ID số thật của Group/Page (10-20 chữ số), không nhập tên như "page" hoặc ID ngắn như "1".'
    return ''


def _normalize_channel_type(value: str) -> str:
    raw = (value or '').strip().lower()
    mapping = {
        'page': 'Page',
        'fanpage': 'Page',
        'video': 'Video',
        'nhom': 'Nhóm',
        'nhóm': 'Nhóm',
        'group': 'Nhóm',
    }
    return mapping.get(raw, (value or 'Nhóm').strip()[:40])


def _clean_managed_channel(body: dict, current: dict | None = None) -> dict:
    current = current or {}
    platform = str(body.get('platform', current.get('platform', '')) or '').strip()[:60]
    channel_name = str(body.get('channel_name', body.get('channel', current.get('channel_name', ''))) or '').strip()[:160]
    channel_type_value = body.get('channel_type', body.get('type', current.get('channel_type', '')))
    channel_type = _normalize_channel_type(str(channel_type_value or 'Nhóm'))
    link = str(body.get('link', current.get('link', '')) or '').strip()[:1000]
    target_id = str(body.get('target_id', body.get('external_id', current.get('target_id', ''))) or '').strip()[:220]
    note = str(body.get('note', current.get('note', '')) or '').strip()[:500]
    if not target_id:
        target_id = _extract_target_id_from_link(link)
    return {
        'platform': platform,
        'channel_name': channel_name,
        'channel_type': channel_type,
        'link': link,
        'target_id': target_id,
        'note': note,
    }


def _resolve_facebook_group_channel(row: dict) -> dict:
    platform = str(row.get('platform') or '').strip().lower()
    channel_type = str(row.get('channel_type') or '').strip().lower()
    target_id = str(row.get('target_id') or '').strip()
    if platform != 'facebook' or channel_type not in ('nhóm', 'nhom', 'group') or not target_id:
        return row
    if re.fullmatch(r'\d{10,20}', target_id):
        return row
    resolved = None
    try:
        resolved = get_api(DEFAULT_GROUP).resolve_slug(target_id)
    except Exception:
        resolved = None
    if not resolved or not resolved.get('id'):
        return row

    next_row = {**row, 'target_id': str(resolved.get('id') or '').strip()}
    if resolved.get('name') and not str(next_row.get('note') or '').strip():
        next_row['note'] = str(resolved.get('name') or '').strip()[:500]
    if not str(next_row.get('channel_name') or '').strip():
        next_row['channel_name'] = str(resolved.get('name') or '').strip()[:160]
    if USE_SUPABASE and next_row.get('id'):
        try:
            sb.update_managed_channel(next_row['id'], next_row, SUPABASE_CHANNEL_TABLE)
        except Exception as e:
            print(f'[supabase] update resolved managed channel failed: {e}')
    return next_row


def _norm_channel_text(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip()).lower()


def _norm_channel_link(value: str) -> str:
    raw = str(value or '').strip().lower()
    raw = re.sub(r'[?#].*$', '', raw)
    return raw.rstrip('/')


def _find_duplicate_managed_channel(row: dict, exclude_id: str = '') -> dict:
    row_platform = _norm_channel_text(row.get('platform', ''))
    row_type = _norm_channel_text(row.get('channel_type', ''))
    row_name = _norm_channel_text(row.get('channel_name', ''))
    row_target = str(row.get('target_id') or '').strip()
    row_link = _norm_channel_link(row.get('link', ''))

    for item in _managed_channels:
        item_id = str(item.get('id') or '')
        if exclude_id and item_id == exclude_id:
            continue
        same_identity = (
            (row_target and row_target == str(item.get('target_id') or '').strip())
            or (row_link and row_link == _norm_channel_link(item.get('link', '')))
        )
        same_name = (
            row_platform
            and row_type
            and row_name
            and row_platform == _norm_channel_text(item.get('platform', ''))
            and row_type == _norm_channel_text(item.get('channel_type', ''))
            and row_name == _norm_channel_text(item.get('channel_name', ''))
        )
        if same_identity or same_name:
            return item
    return {}


def _public_managed_channel(row: dict) -> dict:
    return {
        'id': row.get('id', ''),
        'platform': row.get('platform', ''),
        'channel_name': row.get('channel_name', ''),
        'channel_type': row.get('channel_type', ''),
        'link': row.get('link', ''),
        'target_id': row.get('target_id', ''),
        'note': row.get('note', ''),
        'created_at': row.get('created_at', ''),
        'updated_at': row.get('updated_at', ''),
    }


def _managed_channel_store_error(exc: Exception) -> str:
    detail = str(exc)
    if 'managed_channels' in detail and ('PGRST205' in detail or 'schema cache' in detail or 'Could not find the table' in detail):
        return 'Supabase chưa có bảng managed_channels. Hãy chạy supabase_managed_channels_patch.sql trong SQL Editor rồi thử lại.'
    return detail


def _save_business_profile():
    tmp = BUSINESS_PROFILE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_business_profile, f, ensure_ascii=False)
    os.replace(tmp, BUSINESS_PROFILE_FILE)


def _load_business_profile_from_supabase() -> tuple[dict, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}, 'Chưa cấu hình Supabase'
    try:
        resp = _req.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_PROFILE_TABLE}",
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
            },
            params={'id': 'eq.default', 'select': '*', 'limit': '1'},
            timeout=20,
        )
        if resp.status_code != 200:
            return {}, resp.text[:300]
        rows = resp.json()
        if not rows:
            return {}, ''
        row = rows[0]
        return {
            'business_name': row.get('business_name') or '',
            'phone': row.get('phone') or '',
            'address': row.get('address') or '',
            'why_choose_us': row.get('why_choose_us') or '',
            'extra_notes': row.get('extra_notes') or '',
        }, ''
    except Exception as e:
        return {}, str(e)[:300]


def _save_business_profile_to_supabase(profile: dict) -> tuple[bool, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, 'Chưa cấu hình Supabase'
    payload = {
        'id': 'default',
        'business_name': profile.get('business_name', ''),
        'phone': profile.get('phone', ''),
        'address': profile.get('address', ''),
        'why_choose_us': profile.get('why_choose_us', ''),
        'extra_notes': profile.get('extra_notes', ''),
    }
    try:
        resp = _req.post(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_PROFILE_TABLE}",
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'resolution=merge-duplicates,return=representation',
            },
            params={'on_conflict': 'id'},
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201):
            return True, ''
        return False, (resp.json().get('message') if resp.headers.get('content-type', '').startswith('application/json') else resp.text)[:300]
    except Exception as e:
        return False, str(e)[:300]


def _save_reply_suggestion_to_supabase(suggestion: dict) -> tuple[bool, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, 'Chưa cấu hình Supabase'
    payload = {
        'post_id': suggestion.get('post_id', ''),
        'group_id': suggestion.get('group_id', ''),
        'post_url': suggestion.get('post_url', ''),
        'target_source': suggestion.get('target_source', ''),
        'target_source_id': suggestion.get('target_source_id', ''),
        'customer_name': suggestion.get('customer_name', ''),
        'intent_label': suggestion.get('intent_label', ''),
        'customer_need': suggestion.get('customer_need', ''),
        'buying_stage': suggestion.get('buying_stage', ''),
        'urgency': suggestion.get('urgency', ''),
        'confidence': suggestion.get('confidence', 0),
        'recommended_approach': suggestion.get('recommended_approach', ''),
        'suggested_replies': suggestion.get('suggested_replies', []),
        'raw_ai': suggestion,
    }
    try:
        resp = _req.post(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_REPLY_TABLE}",
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal',
            },
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201, 204):
            return True, ''
        return False, (resp.json().get('message') if resp.headers.get('content-type', '').startswith('application/json') else resp.text)[:300]
    except Exception as e:
        return False, str(e)[:300]


def _save_comment_log_to_supabase(log: dict) -> tuple[bool, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, 'Chưa cấu hình Supabase'
    payload = {
        'staff_id': log.get('staff_id', ''),
        'staff_name': log.get('staff_name', ''),
        'staff_username': log.get('staff_username', ''),
        'facebook_user_id': log.get('facebook_user_id', ''),
        'post_id': log.get('post_id', ''),
        'group_id': log.get('group_id', ''),
        'post_url': log.get('post_url', ''),
        'comment_text': log.get('comment_text', ''),
        'comment_image_url': log.get('comment_image_url', ''),
        'comment_id': log.get('comment_id', ''),
        'page_id': log.get('page_id', ''),
        'status': log.get('status', ''),
        'error_message': log.get('error_message', ''),
        'created_at': log.get('created_at'),
    }
    try:
        resp = _req.post(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_COMMENT_LOG_TABLE}",
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal',
            },
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201, 204):
            return True, ''
        return False, (resp.json().get('message') if resp.headers.get('content-type', '').startswith('application/json') else resp.text)[:300]
    except Exception as e:
        return False, str(e)[:300]


def _save_comment_summary_to_supabase(summary: dict) -> tuple[bool, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, 'Chưa cấu hình Supabase'
    payload = {
        'post_id': summary.get('post_id', ''),
        'group_id': summary.get('group_id', ''),
        'post_url': summary.get('post_url', ''),
        'post_author': summary.get('post_author', ''),
        'post_text': summary.get('post_text', ''),
        'comment_count': summary.get('comment_count', 0),
        'fetched_comment_count': summary.get('fetched_comment_count', 0),
        'comment_authors_count': summary.get('comment_authors_count', 0),
        'summary': summary.get('summary', ''),
        'sentiment': summary.get('sentiment', ''),
        'urgency': summary.get('urgency', ''),
        'main_topics': summary.get('main_topics', []),
        'customer_intents': summary.get('customer_intents', []),
        'top_questions': summary.get('top_questions', []),
        'notable_comments': summary.get('notable_comments', []),
        'lead_signals': summary.get('lead_signals', []),
        'recommended_action': summary.get('recommended_action', ''),
        'spam_or_noise_count': summary.get('spam_or_noise_count', 0),
        'raw_ai': summary,
        'created_by_staff_id': summary.get('created_by_staff_id', ''),
        'created_by_staff_name': summary.get('created_by_staff_name', ''),
        'created_at': summary.get('created_at'),
    }
    try:
        resp = _req.post(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_COMMENT_SUMMARY_TABLE}",
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal',
            },
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201, 204):
            return True, ''
        return False, (resp.json().get('message') if resp.headers.get('content-type', '').startswith('application/json') else resp.text)[:300]
    except Exception as e:
        return False, str(e)[:300]


def _normalize_keywords(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r'[\n,;]+', str(value or ''))
    seen = set()
    keywords = []
    for item in raw:
        kw = str(item or '').strip()
        key = kw.lower()
        if kw and key not in seen:
            seen.add(key)
            keywords.append(kw)
    return keywords[:50]


def _match_comment_keywords(message: str, keywords: list[str]) -> list[str]:
    hay = (message or '').lower()
    return [kw for kw in keywords if kw.lower() in hay]


def _iso_from_unix(value) -> str:
    try:
        ts = int(value or 0)
        if ts <= 0:
            return ''
        return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace('+00:00', 'Z')
    except Exception:
        return ''


def _flatten_facebook_comment_rows(post: dict, comments: list, keywords: list[str], fetched_at: str, staff: dict) -> list[dict]:
    rows: list[dict] = []
    post_id = str(post.get('id') or '')
    page_id = str(post.get('_page_id') or '')
    group_id = str(post.get('_group_id') or page_id or DEFAULT_GROUP)
    post_url = post.get('permalink_url') or ''
    source = 'facebook_page' if page_id else 'facebook'

    def walk(items: list, parent_id: str = '', depth: int = 0):
        for item in items or []:
            if not isinstance(item, dict):
                continue
            cid = str(item.get('id') or '').strip()
            if not cid:
                continue
            from_obj = item.get('from') if isinstance(item.get('from'), dict) else {}
            message = item.get('message') or ''
            matched = _match_comment_keywords(message, keywords)
            rows.append({
                'source': source,
                'post_id': post_id,
                'group_id': group_id,
                'post_url': post_url,
                'comment_id': cid,
                'parent_comment_id': parent_id,
                'depth': depth,
                'author_id': from_obj.get('id') or '',
                'author_name': from_obj.get('name') or 'Ẩn danh',
                'message': message,
                'attachment_type': ((item.get('attachment') or {}).get('type') if isinstance(item.get('attachment'), dict) else '') or '',
                'created_time': item.get('created_time') or None,
                'matched_keywords': matched,
                'is_matched': bool(matched),
                'raw_comment': item,
                'fetched_by_staff_id': staff.get('id', ''),
                'fetched_by_staff_name': staff.get('name', ''),
                'fetched_by_staff_username': staff.get('username', ''),
                'fetched_at': fetched_at,
            })
            replies = ((item.get('comments') or {}).get('data') if isinstance(item.get('comments'), dict) else []) or []
            if replies:
                walk(replies, cid, depth + 1)

    walk(comments)
    return rows


def _save_post_comment_rows_to_supabase(rows: list[dict]) -> tuple[bool, str]:
    if not rows:
        return True, ''
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, 'Chưa cấu hình Supabase'
    deduped_by_comment_id: dict[str, dict] = {}
    for row in rows:
        cid = str(row.get('comment_id') or '').strip()
        if not cid:
            continue
        deduped_by_comment_id[cid] = row
    rows = list(deduped_by_comment_id.values())
    if not rows:
        return True, ''
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates,return=minimal',
    }
    chunk = 200

    def post_chunks(payload_rows: list[dict]) -> tuple[bool, str]:
        for i in range(0, len(payload_rows), chunk):
            resp = _req.post(
                f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_POST_COMMENT_TABLE}?on_conflict=comment_id",
                headers=headers,
                json=payload_rows[i:i + chunk],
                timeout=30,
            )
            if resp.status_code not in (200, 201, 204):
                if resp.headers.get('content-type', '').startswith('application/json'):
                    try:
                        return False, (resp.json().get('message') or resp.text)[:300]
                    except Exception:
                        pass
                return False, resp.text[:300]
        return True, ''

    try:
        ok, error = post_chunks(rows)
        if ok:
            return True, ''
        if "'source' column" in error or 'source column' in error:
            legacy_rows = [{k: v for k, v in row.items() if k != 'source'} for row in rows]
            legacy_ok, legacy_error = post_chunks(legacy_rows)
            if legacy_ok:
                return True, 'Đã lưu Supabase, nhưng bảng post_comments đang thiếu cột source nên chưa phân loại được facebook/tiktok trong DB.'
            return False, legacy_error
        return False, error
    except Exception as e:
        return False, str(e)[:300]


def _store_post_comment_rows(rows: list[dict]) -> tuple[str, str]:
    global _post_comments
    if not rows:
        return 'local', ''
    by_id = {str(item.get('comment_id')): item for item in _post_comments if item.get('comment_id')}
    for row in rows:
        by_id[str(row.get('comment_id'))] = row
    _post_comments = list(by_id.values())[-5000:]
    _save_post_comments()
    _sync_phone_leads_from_comment_rows(rows)
    ok, error = _save_post_comment_rows_to_supabase(rows)
    return ('supabase' if ok else 'local'), error


def _load_post_comment_rows(source: str = '', post_id: str = '', limit: int = 1000) -> tuple[list[dict], str]:
    limit = max(1, min(int(limit or 1000), 5000))
    source = (source or '').strip().lower()
    post_id = (post_id or '').strip()
    if USE_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
        try:
            filters = [
                'select=source,post_id,group_id,post_url,comment_id,parent_comment_id,depth,author_id,author_name,message,attachment_type,created_time,matched_keywords,is_matched,raw_comment,fetched_by_staff_id,fetched_by_staff_name,fetched_by_staff_username,fetched_at',
                'order=fetched_at.desc',
                f'limit={limit}',
            ]
            if source:
                filters.append(f'source=eq.{quote(source, safe="")}')
            if post_id:
                filters.append(f'post_id=eq.{quote(post_id, safe="")}')
            resp = _req.get(
                f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_POST_COMMENT_TABLE}?{'&'.join(filters)}",
                headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
                timeout=30,
            )
            if resp.status_code in (200, 206):
                remote_rows = resp.json()
                if not isinstance(remote_rows, list):
                    remote_rows = []
                by_id = {str(row.get('comment_id') or ''): row for row in remote_rows if row.get('comment_id')}
                for row in _post_comments:
                    if source and str(row.get('source') or 'facebook').lower() != source:
                        continue
                    if post_id and str(row.get('post_id') or '') != post_id:
                        continue
                    cid = str(row.get('comment_id') or '')
                    if cid and cid not in by_id:
                        by_id[cid] = row
                rows = list(by_id.values())
                rows.sort(key=lambda row: row.get('fetched_at') or row.get('created_time') or '', reverse=True)
                return rows[:limit], ''
            return [], resp.text[:300]
        except Exception as e:
            return [], str(e)[:300]
    rows = list(_post_comments)
    if source:
        rows = [row for row in rows if str(row.get('source') or 'facebook').lower() == source]
    if post_id:
        rows = [row for row in rows if str(row.get('post_id') or '') == post_id]
    rows.sort(key=lambda row: row.get('fetched_at') or row.get('created_time') or '', reverse=True)
    return rows[:limit], ''


def _public_comment_row(row: dict) -> dict:
    raw = row.get('raw_comment') if isinstance(row.get('raw_comment'), dict) else {}
    meta = raw.get('_video_meta') if isinstance(raw.get('_video_meta'), dict) else {}
    cid = str(row.get('comment_id') or '')
    post_url = row.get('post_url') or ''
    phones = extract_phones(row.get('message') or '')
    return {
        'source': row.get('source') or '',
        'post_id': row.get('post_id') or '',
        'post_url': post_url,
        'comment_url': f'{post_url}?comment={cid.replace("tiktok_", "")}' if post_url and cid else post_url,
        'comment_id': cid,
        'parent_comment_id': row.get('parent_comment_id') or '',
        'depth': row.get('depth') or 0,
        'author_id': row.get('author_id') or '',
        'author_name': row.get('author_name') or 'Ẩn danh',
        'message': row.get('message') or '',
        'attachment_type': row.get('attachment_type') or '',
        'created_time': row.get('created_time'),
        'matched_keywords': row.get('matched_keywords') or [],
        'is_matched': bool(row.get('is_matched')),
        'phone': phones[0] if phones else '',
        'phones': phones,
        'channel_name': meta.get('channel_name') or _derive_tiktok_channel_name(post_url),
        'video_title': meta.get('video_title') or '',
        'fetched_at': row.get('fetched_at'),
    }


def _extract_tiktok_video_id(raw: str) -> tuple[str, str]:
    value = (raw or '').strip()
    if not value:
        return '', ''
    if re.fullmatch(r'\d{8,}', value):
        return value, f'https://www.tiktok.com/@/video/{value}'

    url = value
    if 'tiktok.com' not in url.lower() and re.search(r'\d{8,}', url):
        vid = re.search(r'\d{8,}', url).group(0)
        return vid, url
    if not re.match(r'^https?://', url, re.I):
        url = 'https://' + url

    final_url = url
    try:
        resp = _req.get(
            url,
            headers={'User-Agent': 'Mozilla/5.0'},
            allow_redirects=True,
            timeout=15,
        )
        final_url = resp.url or url
    except Exception:
        final_url = url

    match = re.search(r'/video/(\d+)', final_url)
    if not match:
        match = re.search(r'(?:item_id|itemId|aweme_id)=(\d+)', final_url)
    return (match.group(1), final_url) if match else ('', final_url)


def _fetch_tiktok_comments(video_id: str, limit: int = 300, cookie: str = '') -> tuple[list[dict], str]:
    comments: list[dict] = []
    cursor = 0
    limit = max(1, min(int(limit or 300), 1000))
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://www.tiktok.com/@/video/{video_id}',
        'Origin': 'https://www.tiktok.com',
    }
    merged_cookie = (cookie or _configured_tiktok_cookie()).strip()
    if merged_cookie:
        headers['Cookie'] = merged_cookie

    def request_page(url: str, params: dict) -> tuple[dict, str]:
        try:
            resp = _req.get(url, params=params, headers=headers, timeout=25)
        except Exception as e:
            return {}, f'Lỗi kết nối TikTok: {str(e)[:180]}'
        if resp.status_code in (401, 403):
            return {}, 'TikTok đang chặn request. Hãy cập nhật TikTok cookie trong menu Cooki rồi chạy lại.'
        if resp.status_code != 200:
            return {}, f'TikTok trả lỗi {resp.status_code}: {resp.text[:160]}'
        try:
            return resp.json(), ''
        except Exception:
            return {}, 'TikTok không trả JSON hợp lệ, có thể endpoint đang bị chặn.'

    def fetch_replies(parent: dict):
        parent_cid = str(parent.get('cid') or parent.get('id') or '').strip()
        if not parent_cid or len(comments) >= limit:
            return ''
        total_replies = int(parent.get('reply_comment_total') or parent.get('reply_comment_count') or 0)
        if total_replies <= 0:
            return ''
        reply_cursor = 0
        while len(comments) < limit:
            reply_count = min(50, limit - len(comments))
            data, error = request_page(
                'https://www.tiktok.com/api/comment/list/reply/',
                {
                    'item_id': video_id,
                    'comment_id': parent_cid,
                    'cursor': reply_cursor,
                    'count': reply_count,
                    'aid': 1988,
                    'app_language': 'vi-VN',
                    'browser_language': 'vi-VN',
                    'device_platform': 'webapp',
                    'region': 'VN',
                    'os': 'windows',
                },
            )
            if error:
                return error
            batch = data.get('comments') or []
            if not batch:
                return ''
            for item in batch:
                if isinstance(item, dict):
                    item['_parent_cid'] = parent_cid
                    item['_depth'] = 1
                    comments.append(item)
                    if len(comments) >= limit:
                        break
            has_more = bool(data.get('has_more'))
            next_cursor = data.get('cursor')
            if not has_more or next_cursor is None or int(next_cursor) == reply_cursor:
                return ''
            reply_cursor = int(next_cursor)
        return ''

    while len(comments) < limit:
        count = min(50, limit - len(comments))
        params = {
            'aweme_id': video_id,
            'cursor': cursor,
            'count': count,
            'aid': 1988,
            'app_language': 'vi-VN',
            'browser_language': 'vi-VN',
            'device_platform': 'webapp',
            'region': 'VN',
            'os': 'windows',
        }
        data, error = request_page('https://www.tiktok.com/api/comment/list/', params)
        if error:
            return comments, error

        batch = data.get('comments') or []
        if not batch:
            msg = data.get('status_msg') or data.get('message') or ''
            return comments, msg or ('Không thấy comment TikTok hoặc video/cookie không có quyền đọc.')
        for item in batch:
            if not isinstance(item, dict):
                continue
            item['_depth'] = 0
            comments.append(item)
            if len(comments) >= limit:
                break
            reply_error = fetch_replies(item)
            if reply_error and not comments:
                return comments, reply_error
            if len(comments) >= limit:
                break
        has_more = bool(data.get('has_more'))
        next_cursor = data.get('cursor')
        if not has_more or next_cursor is None or int(next_cursor) == cursor:
            break
        cursor = int(next_cursor)
    return comments[:limit], ''


def _derive_tiktok_channel_name(video_url: str) -> str:
    match = re.search(r'tiktok\.com/@([^/?#]+)', video_url or '', re.I)
    return f"@{match.group(1).lstrip('@')}" if match else ''


def _flatten_tiktok_comment_rows(
    video_id: str,
    video_url: str,
    comments: list,
    keywords: list[str],
    fetched_at: str,
    staff: dict,
    channel_name: str = '',
    video_title: str = '',
) -> list[dict]:
    rows: list[dict] = []
    post_id = f'tiktok_{video_id}'
    video_meta = {
        'channel_name': channel_name or _derive_tiktok_channel_name(video_url),
        'video_title': video_title or f'Video {video_id}',
        'video_id': video_id,
    }
    for item in comments or []:
        if not isinstance(item, dict):
            continue
        cid = str(item.get('cid') or item.get('id') or '').strip()
        if not cid:
            continue
        depth = int(item.get('_depth') or 0)
        parent_cid = str(item.get('_parent_cid') or '').strip()
        user = item.get('user') if isinstance(item.get('user'), dict) else {}
        share_info = item.get('share_info') if isinstance(item.get('share_info'), dict) else {}
        message = item.get('text') or share_info.get('desc') or ''
        matched = _match_comment_keywords(message, keywords)
        raw_comment = {**item, '_video_meta': video_meta}
        rows.append({
            'source': 'tiktok',
            'post_id': post_id,
            'group_id': '',
            'post_url': video_url,
            'comment_id': f'tiktok_{cid}',
            'parent_comment_id': f'tiktok_{parent_cid}' if parent_cid else '',
            'depth': depth,
            'author_id': str(user.get('uid') or user.get('sec_uid') or ''),
            'author_name': user.get('nickname') or user.get('unique_id') or 'Ẩn danh',
            'message': message,
            'attachment_type': '',
            'created_time': _iso_from_unix(item.get('create_time')) or None,
            'matched_keywords': matched,
            'is_matched': bool(matched),
            'raw_comment': raw_comment,
            'fetched_by_staff_id': staff.get('id', ''),
            'fetched_by_staff_name': staff.get('name', ''),
            'fetched_by_staff_username': staff.get('username', ''),
            'fetched_at': fetched_at,
        })
    return rows


def _tiktok_comment_stats(rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in rows or []:
        if str(row.get('source') or '').lower() != 'tiktok':
            continue
        post_id = str(row.get('post_id') or '')
        if not post_id:
            continue
        public_row = _public_comment_row(row)
        raw = row.get('raw_comment') if isinstance(row.get('raw_comment'), dict) else {}
        meta = raw.get('_video_meta') if isinstance(raw.get('_video_meta'), dict) else {}
        stat = grouped.setdefault(post_id, {
            'post_id': post_id,
            'video_id': post_id.replace('tiktok_', '', 1),
            'post_url': row.get('post_url') or '',
            'channel_name': meta.get('channel_name') or public_row.get('channel_name') or '',
            'video_title': meta.get('video_title') or public_row.get('video_title') or post_id.replace('tiktok_', 'Video '),
            'comment_count': 0,
            'matched_count': 0,
            'phone_count': 0,
            'latest_fetched_at': '',
            'latest_comment_at': '',
            'comments': [],
        })
        if not stat.get('post_url') and row.get('post_url'):
            stat['post_url'] = row.get('post_url')
        if not stat.get('channel_name') and public_row.get('channel_name'):
            stat['channel_name'] = public_row.get('channel_name')
        if not stat.get('video_title') and public_row.get('video_title'):
            stat['video_title'] = public_row.get('video_title')
        stat['comment_count'] += 1
        if public_row.get('is_matched'):
            stat['matched_count'] += 1
        if public_row.get('phones'):
            stat['phone_count'] += 1
        fetched_at = str(public_row.get('fetched_at') or '')
        created_time = str(public_row.get('created_time') or '')
        if fetched_at > str(stat.get('latest_fetched_at') or ''):
            stat['latest_fetched_at'] = fetched_at
        if created_time > str(stat.get('latest_comment_at') or ''):
            stat['latest_comment_at'] = created_time
        stat['comments'].append(public_row)

    stats = list(grouped.values())
    for stat in stats:
        stat['comments'].sort(key=lambda row: row.get('created_time') or row.get('fetched_at') or '', reverse=True)
    stats.sort(key=lambda item: item.get('latest_fetched_at') or item.get('latest_comment_at') or '', reverse=True)
    return stats


def _send_tiktok_comment(video_id: str, video_url: str, message: str, cookie: str = '') -> tuple[dict, str]:
    message = (message or '').strip()
    if not message:
        return {}, 'Nhập nội dung bình luận TikTok'
    merged_cookie = (cookie or _configured_tiktok_cookie()).strip()
    if not merged_cookie:
        return {}, 'Thiếu cookie TikTok. Admin cần nhập TikTok cookie trong menu Cooki.'
    if not _has_tiktok_login_cookie(merged_cookie):
        return {}, _tiktok_cookie_login_message(merged_cookie)

    csrf = (
        _extract_cookie_value(merged_cookie, 'tt_csrf_token')
        or _extract_cookie_value(merged_cookie, 'csrf_session_id')
    )
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': video_url or f'https://www.tiktok.com/@/video/{video_id}',
        'Origin': 'https://www.tiktok.com',
        'Cookie': merged_cookie,
    }
    if csrf:
        headers['X-Secsdk-Csrf-Token'] = csrf
        headers['x-secsdk-csrf-token'] = csrf

    params = {
        'aweme_id': video_id,
        'aid': 1988,
        'app_language': 'vi-VN',
        'browser_language': 'vi-VN',
        'device_platform': 'webapp',
        'region': 'VN',
        'os': 'windows',
    }
    data = {
        'aweme_id': video_id,
        'text': message,
    }
    try:
        resp = _req.post(
            'https://www.tiktok.com/api/comment/publish/',
            params=params,
            headers=headers,
            data=data,
            timeout=30,
        )
    except Exception as e:
        return {}, f'Lỗi kết nối TikTok: {str(e)[:180]}'

    if resp.status_code in (401, 403):
        return {}, 'TikTok chặn gửi bình luận. Cookie có thể hết hạn, thiếu CSRF hoặc tài khoản không có quyền bình luận video này.'
    if resp.status_code != 200:
        return {}, f'TikTok trả lỗi {resp.status_code}: {resp.text[:180]}'
    try:
        payload = resp.json()
    except Exception:
        return {}, 'TikTok không trả JSON hợp lệ khi gửi bình luận.'

    status_code = payload.get('status_code')
    if status_code not in (0, '0', None) or payload.get('status_msg') or payload.get('message'):
        msg = payload.get('status_msg') or payload.get('message') or payload.get('log_pb') or 'TikTok không nhận bình luận'
        if status_code in (0, '0') and (payload.get('comment') or payload.get('comments')):
            return payload, ''
        return {}, _friendly_tiktok_publish_error(str(msg)[:220])
    return payload, ''


def _record_tiktok_extension_comment(body: dict) -> tuple[dict, int]:
    raw_url = str(body.get('url') or body.get('video_url') or body.get('post_url') or '').strip()
    raw_video_id = str(body.get('video_id') or '').strip()
    post_id = str(body.get('post_id') or '').strip()
    message = str(body.get('message') or body.get('text') or '').strip()
    status = str(body.get('status') or '').strip().lower()
    error = str(body.get('error') or '').strip()
    extension_result = body.get('extension_result') if isinstance(body.get('extension_result'), dict) else {}

    if post_id.startswith('tiktok_') and not raw_video_id:
        raw_video_id = post_id.replace('tiktok_', '', 1)
    video_id, final_url = _extract_tiktok_video_id(raw_video_id or raw_url)
    if not video_id:
        return {'ok': False, 'error': 'Không nhận diện được video TikTok để ghi lịch sử.'}, 400
    if not message:
        return {'ok': False, 'error': 'Thiếu nội dung bình luận TikTok'}, 400
    if not final_url:
        final_url = raw_url or f'https://www.tiktok.com/@/video/{video_id}'

    final_post_id = f'tiktok_{video_id}'
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    staff = _current_staff()

    if status != 'success':
        log = _record_comment_log(
            final_post_id,
            'tiktok',
            final_url,
            message,
            'tiktok-extension',
            'failed',
            error_message=error or 'Extension chưa gửi được bình luận TikTok',
        )
        res = {
            'ok': False,
            'source': 'tiktok',
            'post_id': final_post_id,
            'post_url': final_url,
            'error': error or 'Extension chưa gửi được bình luận TikTok',
            'log_storage': log.get('storage'),
        }
        if log.get('storage_warning'):
            res['warning'] = f"Đã lưu local, Supabase chưa ghi được: {log['storage_warning']}"
        return res, 200

    comment_id = str(
        body.get('comment_id')
        or extension_result.get('comment_id')
        or extension_result.get('cid')
        or extension_result.get('id')
        or f'extension_{uuid.uuid4().hex}'
    )
    if not comment_id.startswith('tiktok_'):
        comment_id = f'tiktok_{comment_id}'

    log = _record_comment_log(final_post_id, 'tiktok', final_url, message, 'tiktok-extension', 'success', comment_id=comment_id)
    rows = [{
        'source': 'tiktok',
        'post_id': final_post_id,
        'group_id': '',
        'post_url': final_url,
        'comment_id': comment_id,
        'parent_comment_id': '',
        'depth': 0,
        'author_id': staff.get('id', ''),
        'author_name': staff.get('name') or staff.get('username') or 'Nhân sự',
        'message': message,
        'attachment_type': '',
        'created_time': now,
        'matched_keywords': [],
        'is_matched': False,
        'raw_comment': {
            'outbound': True,
            'delivery': 'chrome_extension',
            'extension_result': extension_result,
            '_video_meta': {
                'channel_name': str(body.get('channel_name') or _derive_tiktok_channel_name(final_url)),
                'video_title': str(body.get('video_title') or f'Video {video_id}'),
                'video_id': video_id,
            },
        },
        'fetched_by_staff_id': staff.get('id', ''),
        'fetched_by_staff_name': staff.get('name', ''),
        'fetched_by_staff_username': staff.get('username', ''),
        'fetched_at': now,
    }]
    storage, storage_warning = _store_post_comment_rows(rows)
    res = {
        'ok': True,
        'source': 'tiktok',
        'post_id': final_post_id,
        'post_url': final_url,
        'comment_id': comment_id,
        'delivery': 'chrome_extension',
        'storage': storage,
        'log_storage': log.get('storage'),
    }
    warnings = []
    if storage_warning:
        warnings.append(f'Comment đã gửi, nhưng Supabase post_comments chưa ghi được: {storage_warning}')
    if log.get('storage_warning'):
        warnings.append(f"Lịch sử comment đã lưu local, Supabase chưa ghi được: {log['storage_warning']}")
    if warnings:
        res['warning'] = ' | '.join(warnings)
    return res, 200


def _upload_comment_image_to_supabase(file_storage) -> tuple[str, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return '', 'Chưa cấu hình Supabase'
    if not file_storage or not file_storage.filename:
        return '', 'Chưa chọn file ảnh'

    content_type = (file_storage.mimetype or '').lower()
    if content_type not in ALLOWED_COMMENT_IMAGE_TYPES:
        return '', 'Chỉ hỗ trợ ảnh JPG, PNG, WEBP hoặc GIF'

    content = file_storage.read()
    if not content:
        return '', 'File ảnh rỗng'
    if len(content) > MAX_COMMENT_IMAGE_BYTES:
        return '', f'Ảnh quá lớn, tối đa {MAX_COMMENT_IMAGE_BYTES // (1024 * 1024)}MB'

    original = secure_filename(file_storage.filename or 'comment-image')
    _, original_ext = os.path.splitext(original)
    ext = original_ext.lower() if original_ext.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'} else ALLOWED_COMMENT_IMAGE_TYPES[content_type]
    if ext == '.jpeg':
        ext = '.jpg'

    staff_id = _current_staff_id() or 'anonymous'
    try:
        tz = ZoneInfo(APP_TIMEZONE)
    except Exception:
        tz = ZoneInfo('Asia/Ho_Chi_Minh')
    today = datetime.now(tz).strftime('%Y/%m/%d')
    object_path = f'{today}/{staff_id}/{uuid.uuid4().hex}{ext}'
    upload_url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{SUPABASE_COMMENT_IMAGE_BUCKET}/{object_path}"

    try:
        resp = _req.post(
            upload_url,
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': content_type,
                'x-upsert': 'false',
            },
            data=content,
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            message = resp.text[:300]
            if resp.headers.get('content-type', '').startswith('application/json'):
                try:
                    message = resp.json().get('message') or message
                except Exception:
                    pass
            return '', message
        public_path = quote(object_path, safe='/')
        public_url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{SUPABASE_COMMENT_IMAGE_BUCKET}/{public_path}"
        return public_url, ''
    except Exception as e:
        return '', str(e)[:300]


def _record_comment_log(post_id: str, group_id: str, post_url: str, message: str, page_id: str,
                        status: str, comment_id: str = '', error_message: str = '', image_url: str = '') -> dict:
    global _comment_logs
    staff = _current_staff()
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    log = {
        'staff_id': staff.get('id', ''),
        'staff_name': staff.get('name', ''),
        'staff_username': staff.get('username', ''),
        'facebook_user_id': _extract_cookie_user(staff.get('cookie', '')),
        'post_id': post_id,
        'group_id': group_id,
        'post_url': post_url,
        'comment_text': message,
        'comment_image_url': image_url,
        'comment_id': comment_id,
        'page_id': page_id,
        'status': status,
        'error_message': error_message,
        'created_at': now,
    }
    _comment_logs.append(log)
    _save_comment_logs()
    supabase_ok, supabase_error = _save_comment_log_to_supabase(log)
    log['storage'] = 'supabase' if supabase_ok else 'local'
    if supabase_error:
        log['storage_warning'] = supabase_error
    return log


def _today_utc_bounds() -> tuple[datetime, datetime]:
    try:
        tz = ZoneInfo(APP_TIMEZONE)
    except Exception:
        tz = ZoneInfo('Asia/Ho_Chi_Minh')
    today = datetime.now(tz).date()
    start_local = datetime.combine(today, time.min, tzinfo=tz)
    end_local = datetime.combine(today, time.max, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _today_local_key() -> str:
    try:
        tz = ZoneInfo(APP_TIMEZONE)
    except Exception:
        tz = ZoneInfo('Asia/Ho_Chi_Minh')
    return datetime.now(tz).date().isoformat()


def _track_scanned(count: int) -> None:
    """Cộng số bài đã quét trong ngày để phục vụ KPI dashboard."""
    if count <= 0:
        return
    key = _today_local_key()
    _scan_counter[key] = _scan_counter.get(key, 0) + count
    # Giữ tối đa 14 ngày gần nhất để tránh phình bộ nhớ
    if len(_scan_counter) > 14:
        for old_key in sorted(_scan_counter.keys())[:-14]:
            _scan_counter.pop(old_key, None)


def _count_scanned_today() -> int:
    return int(_scan_counter.get(_today_local_key(), 0))


def _parse_log_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except Exception:
        return None


def _count_today_success_local(staff_id: str = '') -> int:
    start_utc, end_utc = _today_utc_bounds()
    count = 0
    for item in _comment_logs:
        if item.get('status') != 'success':
            continue
        if staff_id and item.get('staff_id') != staff_id:
            continue
        created_at = _parse_log_time(item.get('created_at', ''))
        if created_at and start_utc <= created_at <= end_utc:
            count += 1
    return count


def _count_today_success_supabase(staff_id: str = '') -> tuple[int | None, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, 'Chưa cấu hình Supabase'
    start_utc, end_utc = _today_utc_bounds()
    params = [
        ('select', 'id'),
        ('status', 'eq.success'),
        ('created_at', f'gte.{start_utc.isoformat()}'),
        ('created_at', f'lte.{end_utc.isoformat()}'),
    ]
    if staff_id:
        params.append(('staff_id', f'eq.{staff_id}'))
    try:
        resp = _req.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_COMMENT_LOG_TABLE}",
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Prefer': 'count=exact',
                'Range': '0-0',
            },
            params=params,
            timeout=20,
        )
        if resp.status_code not in (200, 206):
            return None, resp.text[:300]
        content_range = resp.headers.get('content-range') or resp.headers.get('Content-Range') or ''
        if '/' in content_range:
            return int(content_range.rsplit('/', 1)[-1]), ''
        return len(resp.json()), ''
    except Exception as e:
        return None, str(e)[:300]


def _get_ai_key(provider: str) -> str:
    stored_key = (_ai_config.get('keys') or {}).get(provider, '')
    env_keys = {
        'gemini': 'GEMINI_API_KEY',
        'openai': 'OPENAI_API_KEY',
        'claude': 'CLAUDE_API_KEY',
    }
    return stored_key or os.environ.get(env_keys.get(provider, ''), '') or DEFAULT_API_KEY


def _get_classifier() -> AIClassifier:
    provider = _ai_config.get('provider', 'gemini')
    default_model = PROVIDERS.get(provider, {}).get('default_model', DEFAULT_MODEL)
    model = _ai_config.get('model', default_model) or default_model
    api_key = _get_ai_key(provider)
    categories = _ai_config.get('categories', DEFAULT_CATEGORIES)
    return AIClassifier(provider, model, api_key, categories)


def get_api(group_id: str) -> FacebookGroupAPI:
    staff_id = _active_staff_id()
    cache_key = f'{staff_id or "default"}:{group_id}'
    if cache_key not in _api_cache:
        token_file = _staff_token_file(staff_id) if staff_id else None
        _api_cache[cache_key] = FacebookGroupAPI(group_id, cookie=_active_cookie(), token_file=token_file)
    return _api_cache[cache_key]


@app.before_request
def _require_auth_for_api():
    if request.method == 'OPTIONS':
        return None
    public_endpoints = {'auth_status', 'auth_login', 'auth_setup'}
    if request.path.startswith('/api/') and request.endpoint not in public_endpoints:
        if _setup_required():
            return jsonify({'ok': False, 'error': 'Cần setup tài khoản đầu tiên', 'setup_required': True}), 401
        if not _current_staff():
            return jsonify({'ok': False, 'error': 'Vui lòng đăng nhập', 'auth_required': True}), 401


# ── Telegram ───────────────────────────────────────────
def _tg_send(chat_id: str, text: str):
    if not BOT_TOKEN:
        return
    try:
        _req.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown',
                  'disable_web_page_preview': False},
            timeout=10,
        )
    except Exception:
        pass


def _notify_new_post(post: dict):
    if not _tg_chat_ids:
        return
    author = (post.get('from') or {}).get('name', 'Ẩn danh')
    text = post.get('message', '') or ''
    preview = text[:300] + ('...' if len(text) > 300 else '')
    msg = (
        f"🔔 *Bài mới trong nhóm* `{post.get('_group_id', '')}`\n\n"
        f"👤 *{author}*\n{preview}\n\n"
        f"[🔗 Xem bài viết]({post.get('permalink_url', '')})"
    )
    for cid in _tg_chat_ids:
        _tg_send(cid, msg)


def _tg_broadcast(msg: str):
    """Gửi message tới toàn bộ chat id đã đăng ký."""
    for cid in _tg_chat_ids:
        _tg_send(cid, msg)


def _lead_link(lead: dict) -> str:
    return str(lead.get('comment_url') or lead.get('post_url') or '').strip()


def _notify_hot_lead(lead: dict):
    """Thông báo Telegram khi có lead nóng/rất nóng (đặc tả Bước 7)."""
    if not _tg_chat_ids:
        return
    level = str(lead.get('lead_level') or '')
    if level not in ('hot', 'very_hot'):
        return
    icon = '🔴🔥' if level == 'very_hot' else '🟠🔥'
    label = lead.get('lead_level_label') or ('Lead rất nóng' if level == 'very_hot' else 'Lead nóng')
    sla = _lead_sla_minutes(level)
    assigned = lead.get('assigned_sale_name') or 'Chưa chia'
    link = _lead_link(lead)
    msg = (
        f"{icon} *{label}* — {lead.get('lead_score', 0)} điểm\n\n"
        f"👤 *{lead.get('name') or 'Ẩn danh'}*\n"
        f"📝 {(lead.get('need') or lead.get('evidence') or '')[:280]}\n"
        f"📞 {lead.get('phone') or 'Chưa có SĐT'}\n"
        f"🧑‍💼 Sale: {assigned}\n"
        f"⏱ SLA: {sla} phút\n"
    )
    if link:
        msg += f"\n[🔗 Mở bài/bình luận]({link})"
    _tg_broadcast(msg)


def _notify_sla_escalation(lead: dict, reason: str):
    """Cảnh báo escalation khi lead quá hạn SLA (đặc tả Bước 7)."""
    if not _tg_chat_ids:
        return
    label = lead.get('lead_level_label') or lead.get('lead_level') or 'Lead'
    assigned = lead.get('assigned_sale_name') or 'Chưa chia'
    link = _lead_link(lead)
    msg = (
        f"⚠️ *CẢNH BÁO SLA* — {reason}\n\n"
        f"👤 *{lead.get('name') or 'Ẩn danh'}* ({label}, {lead.get('lead_score', 0)} điểm)\n"
        f"📞 {lead.get('phone') or 'Chưa có SĐT'}\n"
        f"🧑‍💼 Sale phụ trách: {assigned}\n"
        f"📌 Trạng thái: {lead.get('lead_status') or 'new'}\n"
    )
    if link:
        msg += f"\n[🔗 Mở lead]({link})"
    _tg_broadcast(msg)


def _poll_telegram():
    if not BOT_TOKEN:
        return
    offset = 0
    while True:
        try:
            r = _req.get(
                f'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates',
                params={'offset': offset, 'timeout': 30},
                timeout=35,
            )
            for upd in r.json().get('result', []):
                offset = upd['update_id'] + 1
                msg = upd.get('message', {})
                if msg.get('text', '').startswith('/start'):
                    cid = str(msg['chat']['id'])
                    name = msg['from'].get('first_name', '')
                    _tg_send(cid,
                        f"👋 Xin chào {name}\\!\n\n"
                        f"Chat ID của bạn là:\n`{cid}`\n\n"
                        f"Copy ID này rồi vào web thêm vào mục *Telegram* để nhận thông báo\\."
                    )
        except Exception:
            pass


# Lưu các lead đã escalation để không báo trùng: {lead_key: 'overdue'}
_escalated_leads: dict = {}


def _sla_monitor_tick():
    """Quét các lead chưa xử lý, escalation khi quá SLA (đặc tả Bước 7).

    - Lead nóng/rất nóng quá hạn: chuyển sang sale khác + báo giám đốc (toàn bộ chat id).
    - Chỉ áp dụng cho lead còn ở trạng thái chưa liên hệ (new/assigned).
    """
    try:
        grouped, _warning = _load_leads_from_supabase()
        rows = _flatten_lead_groups(grouped or _leads)
    except Exception:
        rows = _flatten_lead_groups(_leads)

    now = datetime.now(timezone.utc)
    for lead in rows:
        status = str(lead.get('lead_status') or 'new')
        if status not in ('new', 'assigned', 'not_contacted', ''):
            _escalated_leads.pop(str(lead.get('lead_key') or ''), None)
            continue
        due = _parse_dt(str(lead.get('sla_due_at') or ''))
        if not due:
            continue
        overdue = (now - due.astimezone(timezone.utc)).total_seconds() > 0
        if not overdue:
            continue
        key = str(lead.get('lead_key') or '')
        if _escalated_leads.get(key) == 'overdue':
            continue  # đã escalation rồi

        level = str(lead.get('lead_level') or '')
        reason = f"Quá SLA {lead.get('sla_minutes', 0)} phút chưa đổi trạng thái"
        # Lead nóng/rất nóng: tự chuyển sang sale khác
        if level in ('hot', 'very_hot'):
            other = _pick_other_sale(str(lead.get('assigned_sale_id') or ''))
            if other and other.get('id') != str(lead.get('assigned_sale_id') or ''):
                lead['assigned_sale_id'] = other['id']
                lead['assigned_sale_name'] = other['name']
                _append_status_history(lead, status, note=f'Chuyển sale do quá SLA → {other["name"]}', by='system')
                updated = _normalise_lead({**lead, 'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z'}, lead.get('post_id') or '')
                _update_lead_in_memory(key, {
                    'assigned_sale_id': updated.get('assigned_sale_id'),
                    'assigned_sale_name': updated.get('assigned_sale_name'),
                    'status_history': updated.get('status_history'),
                })
                _patch_lead_in_supabase(key, updated)
                reason += f"; đã chuyển cho {other['name']}"
        _notify_sla_escalation(lead, reason)
        _escalated_leads[key] = 'overdue'


def _sla_monitor_loop():
    """Vòng lặp nền kiểm tra SLA mỗi phút."""
    while True:
        try:
            if _settings.get('sla_monitor', True):
                _sla_monitor_tick()
        except Exception as e:
            print(f'[sla] monitor error: {e}')
        _time.sleep(60)


# ── Scheduler quét bài tự động phía server (đặc tả Bước 1) ──
_last_auto_scan_at: dict = {'value': ''}


def _scan_page_ids() -> list[str]:
    """Lấy danh sách Page Facebook đã cấu hình để quét."""
    ids = []
    for row in _managed_channels:
        platform = str(row.get('platform') or '').strip().lower()
        channel_type = str(row.get('channel_type') or '').strip().lower()
        target_id = str(row.get('target_id') or '').strip()
        if platform == 'facebook' and channel_type in ('trang', 'page') and target_id:
            ids.append(target_id)
    return ids


def _auto_scan_tick():
    """Quét toàn bộ group/page đã cấu hình, tự phân loại và tách lead nếu được bật."""
    group_ids = [g['id'] for g in _merged_facebook_groups() if g.get('id')]
    page_ids = _scan_page_ids()
    summary = {
        'ok': True,
        'group_count': len(group_ids),
        'page_count': len(page_ids),
        'post_count': 0,
        'lead_count': 0,
        'report': [],
        'message': '',
    }
    if not group_ids and not page_ids:
        summary['message'] = 'Chưa có group/page được cấu hình để quét.'
        return summary
    limit = int(_settings.get('interval_post_limit', 15) or 15)
    all_posts, _report = _scan_targets(group_ids, page_ids, limit, notify=True)
    summary['post_count'] = len(all_posts or [])
    summary['report'] = _report or []
    _last_auto_scan_at['value'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    summary['last_auto_scan_at'] = _last_auto_scan_at['value']
    if not all_posts:
        summary['message'] = 'Đã quét nhưng chưa lấy được bài mới từ các kênh.'
        return summary

    # Tự tách lead nếu bật auto_classify (dùng chung cấu hình AI)
    if not _ai_config.get('auto_classify'):
        summary['message'] = 'Đã quét bài. Chưa tách lead vì AI tự động đang tắt.'
        return summary
    classifier = _get_classifier()
    if not classifier.api_key:
        summary['message'] = 'Đã quét bài. Chưa tách lead vì chưa cấu hình API key AI.'
        return summary
    to_extract = [p for p in all_posts if p.get('id') and p.get('id') not in _leads]
    if not to_extract:
        summary['message'] = 'Đã quét bài. Không có bài mới cần tách lead.'
        return summary
    try:
        results = classifier.extract_leads(to_extract)
    except Exception as e:
        print(f'[auto-scan] extract leads error: {e}')
        summary['ok'] = False
        summary['message'] = f'Lỗi tách lead AI: {e}'
        return summary
    posts_by_id = {str(p.get('id') or ''): p for p in to_extract}
    lead_count = 0
    for post in to_extract:
        pid = post.get('id')
        if pid:
            processed = _postprocess_new_leads(
                [_normalise_lead(item, pid) for item in results.get(pid, [])],
                posts_by_id=posts_by_id,
            )
            _leads[pid] = processed
            lead_count += len(processed)
    _save_leads()
    flat_leads = [lead for items in _leads.values() for lead in (items or []) if str(lead.get('post_id') or '') in posts_by_id]
    _save_leads_to_supabase(flat_leads)
    summary['lead_count'] = lead_count
    summary['message'] = f'Đã quét {summary["post_count"]} bài và tách {lead_count} lead.'
    return summary


def _auto_scan_loop():
    """Vòng lặp nền quét bài theo chu kỳ (mặc định 5 phút). Cần bật server_auto_scan."""
    while True:
        interval_min = 5
        try:
            interval_min = max(1, int(_settings.get('scan_interval_min', _settings.get('interval', 5)) or 5))
            if _settings.get('server_auto_scan', False):
                _auto_scan_tick()
        except Exception as e:
            print(f'[auto-scan] loop error: {e}')
        _time.sleep(interval_min * 60)


# ── Routes ─────────────────────────────────────────────
@app.route('/')
def index():
    if USE_LEGACY_UI:
        return render_template('index.html')
    from flask import redirect
    return redirect(WEB_UI_URL)


@app.route('/api/auth/status')
def auth_status():
    staff = _public_current_staff()
    return jsonify({
        'ok': True,
        'authenticated': bool(staff),
        'setup_required': _setup_required(),
        'simple_login': SIMPLE_LOGIN_ONLY,
        'staff': staff,
        'can_manage': _is_admin(),
    })


@app.route('/api/auth/setup', methods=['POST'])
def auth_setup():
    global _staff_cookies
    body = request.get_json() or {}
    name = str(body.get('name') or '').strip()[:80]
    username = str(body.get('username') or '').strip().lower()[:60]
    password = str(body.get('password') or '')
    cookie = str(body.get('cookie') or '').strip()
    if not _setup_required():
        existing = next((item for item in _staff_accounts()
                         if item.get('enabled', True) and item.get('username') == username), None)
        if existing and _verify_password(password, existing.get('password_salt', ''), existing.get('password_hash', '')):
            _set_logged_in_staff(existing)
            _invalidate_facebook_cache()
            return jsonify({'ok': True, 'already_setup': True, 'staff': _public_current_staff(), 'can_manage': _is_admin()})
        return jsonify({
            'ok': False,
            'already_setup': True,
            'setup_required': False,
            'error': 'Hệ thống đã có admin. Vui lòng đăng nhập bằng tài khoản đã tạo.',
        }), 409
    if not name or not username or not password or not cookie:
        return jsonify({'ok': False, 'error': 'Nhập đủ tên, tài khoản, mật khẩu và cookie'}), 400
    if len(password) < 6:
        return jsonify({'ok': False, 'error': 'Mật khẩu tối thiểu 6 ký tự'}), 400
    if 'c_user=' not in cookie:
        return jsonify({'ok': False, 'error': 'Cookie chưa có c_user, vui lòng kiểm tra lại'}), 400

    salt, digest = _hash_password(password)
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    staff_id = uuid.uuid4().hex[:12]
    _staff_cookies = {
        'active_staff_id': staff_id,
        'staff': [{
            'id': staff_id,
            'name': name,
            'username': username,
            'password_salt': salt,
            'password_hash': digest,
            'cookie': cookie,
            'role': 'admin',
            'enabled': True,
            'created_at': now,
            'updated_at': now,
        }]
    }
    _save_staff_cookies()
    _set_logged_in_staff(_staff_cookies['staff'][0])
    _invalidate_facebook_cache()
    return jsonify({'ok': True, 'staff': _public_current_staff(), 'can_manage': _is_admin()})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    body = request.get_json() or {}
    username = str(body.get('username') or '').strip().lower()
    password = str(body.get('password') or '')
    if not username or not password:
        return jsonify({'ok': False, 'error': 'Nhập tài khoản và mật khẩu'}), 400

    staff = _find_local_staff(username)
    if staff and _verify_password(password, staff.get('password_salt', ''), staff.get('password_hash', '')):
        _set_logged_in_staff(staff)
        _invalidate_facebook_cache()
        return jsonify({'ok': True, 'staff': _public_current_staff(), 'can_manage': _is_admin()})

    row, supabase_error = _load_supabase_staff(username)
    if row:
        supabase_staff = _normalize_supabase_staff(row)
        if not supabase_staff.get('enabled', True):
            return jsonify({'ok': False, 'error': 'Tài khoản đã bị tắt'}), 403
        if _supabase_password_matches(row, password):
            _set_logged_in_staff(supabase_staff)
            _invalidate_facebook_cache()
            return jsonify({'ok': True, 'staff': _public_current_staff(), 'can_manage': _is_admin()})
        return jsonify({'ok': False, 'error': 'Sai tài khoản hoặc mật khẩu'}), 401

    if supabase_error and 'Could not find the table' in supabase_error:
        return jsonify({
            'ok': False,
            'error': f'Chưa có bảng {SUPABASE_STAFF_TABLE} trong Supabase. Chạy lại file SQL rồi thêm user/pass.',
        }), 500
    if supabase_error and 'Could not find the' in supabase_error:
        return jsonify({'ok': False, 'error': f'Lỗi bảng đăng nhập Supabase: {supabase_error}'}), 500

    return jsonify({'ok': False, 'error': 'Sai tài khoản hoặc mật khẩu'}), 401


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    _clear_logged_in_staff()
    _invalidate_facebook_cache()
    return jsonify({'ok': True})


def _scan_targets(group_ids: list[str], page_ids: list[str], limit: int = 10, notify: bool = True) -> tuple[list[dict], list[dict]]:
    """Lõi quét bài dùng chung cho route /api/posts và scheduler nền.

    Trả về (all_posts, report). Cập nhật _seen_ids, gửi thông báo bài mới, đếm bài quét.
    """
    global _seen_ids
    is_first = len(_seen_ids) == 0
    all_posts: list[dict] = []
    report: list[dict] = []

    for gid in group_ids:
        posts = get_api(gid).get_posts(limit)
        if posts is None:
            report.append({
                'group_id': gid,
                'group_name': next((g.get('name') for g in _merged_facebook_groups() if g.get('id') == gid), gid),
                'ok': False,
                'count': 0,
                'source': 'facebook_graph',
                'error': 'Cookie hết hạn, chưa vào nhóm, hoặc Facebook không cho đọc feed nhóm này',
            })
            continue
        for p in posts:
            p['_group_id'] = gid
            p['_source'] = 'facebook_graph'
        all_posts.extend(posts)
        report.append({
            'group_id': gid,
            'target_type': 'group',
            'target_id': gid,
            'group_name': next((g.get('name') for g in _merged_facebook_groups() if g.get('id') == gid), gid),
            'ok': True,
            'count': len(posts or []),
            'source': 'facebook_graph',
            'error': '',
        })

    for page_id in page_ids:
        page_name = next((item.get('channel_name') for item in _managed_channels if str(item.get('target_id') or '') == page_id), '')
        try:
            page_token = _page_token_from_cache(page_id)
            if not page_token:
                raise RuntimeError('Không lấy được Page token')
            posts = get_api(DEFAULT_GROUP).get_page_posts(page_id, page_token, limit)
        except Exception:
            posts = None
        if posts is None:
            report.append({
                'group_id': page_id,
                'target_type': 'page',
                'target_id': page_id,
                'group_name': page_name or page_id,
                'ok': False,
                'count': 0,
                'source': 'facebook_page_graph',
                'error': 'Không đọc được bài từ Page. Kiểm tra quyền quản trị Page và cookie.',
            })
            continue
        for p in posts:
            p['_page_id'] = page_id
            p['_page_name'] = page_name or (_pages_cache.get(page_id) or {}).get('name') or page_id
            p['_source'] = 'facebook_page_graph'
        all_posts.extend(posts)
        report.append({
            'group_id': page_id,
            'target_type': 'page',
            'target_id': page_id,
            'group_name': page_name or (_pages_cache.get(page_id) or {}).get('name') or page_id,
            'ok': True,
            'count': len(posts or []),
            'source': 'facebook_page_graph',
            'error': '',
        })

    all_posts.sort(key=lambda x: x.get('created_time', ''), reverse=True)

    new_ids = set()
    new_posts = []
    for post in all_posts:
        pid = post.get('id')
        if pid and pid not in _seen_ids:
            new_ids.add(pid)
            new_posts.append(post)
            if notify and not is_first:
                threading.Thread(target=_notify_new_post, args=(post,), daemon=True).start()

    if new_ids:
        _seen_ids.update(new_ids)
        _save_seen(new_posts)
    _track_scanned(len(all_posts))
    return all_posts, report


@app.route('/api/posts')
def api_posts():
    limit = request.args.get('limit', 10, type=int)
    group_ids = [g.strip() for g in request.args.get('groups', DEFAULT_GROUP).split(',') if g.strip()]
    page_ids = [p.strip() for p in request.args.get('pages', '').split(',') if p.strip()]
    debug = request.args.get('debug', '').lower() in ('1', 'true', 'yes')
    invalid_group_ids = [gid for gid in group_ids if not _is_valid_facebook_numeric_id(gid)]
    if invalid_group_ids:
        return jsonify({
            'error': 'Danh sách nhóm có ID không hợp lệ. Hãy xoá nhóm sai rồi thêm lại bằng ID số thật.',
            'invalid_groups': invalid_group_ids,
            'posts': [],
            'report': [{
                'group_id': gid,
                'group_name': gid,
                'ok': False,
                'count': 0,
                'source': 'facebook_graph',
                'error': 'ID nhóm không hợp lệ',
            } for gid in invalid_group_ids],
            'source': 'facebook_graph',
        }), 400

    try:
        all_posts, report = _scan_targets(group_ids, page_ids, limit)

        if (group_ids or page_ids) and not all_posts and any(not item.get('ok') for item in report):
            payload = {
                'error': 'Không lấy được bài từ Facebook. Kiểm tra cookie nhân sự, quyền nhóm/Page và quyền quản trị Page.',
                'posts': [],
                'report': report,
                'source': 'facebook_graph',
            }
            return jsonify(payload), 401

        if debug:
            return jsonify({
                'ok': True,
                'source': 'facebook_graph',
                'posts': all_posts,
                'report': report,
                'total_posts': len(all_posts),
            })
        return jsonify(all_posts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/post', methods=['POST'])
def api_create_post():
    body = request.get_json() or {}
    group_id = body.get('group_id', '').strip()
    message = body.get('message', '').strip()
    page_id = body.get('page_id', '').strip()
    if not group_id or not message:
        return jsonify({'ok': False, 'error': 'Thiếu group_id hoặc message'}), 400
    try:
        page_token = _pages_cache.get(page_id, {}).get('access_token') if page_id else None
        result = get_api(group_id).create_post(message, page_token)
        if result and 'id' in result:
            return jsonify({'ok': True, 'post_id': result['id']})
        err = (result or {}).get('error', {}).get('message', 'Lỗi không xác định')
        return jsonify({'ok': False, 'error': err})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/page-post', methods=['POST'])
def api_create_page_post():
    body = request.get_json() or {}
    page_id = str(body.get('page_id') or '').strip()
    message = str(body.get('message') or '').strip()
    if not page_id or not message:
        return jsonify({'ok': False, 'error': 'Thiếu page_id hoặc message'}), 400
    try:
        page_token = _page_token_from_cache(page_id)
        if not page_token:
            return jsonify({'ok': False, 'error': 'Không lấy được Page token. Kiểm tra quyền quản trị Page/cookie.'}), 400
        result = get_api(DEFAULT_GROUP).create_page_post(page_id, message, page_token)
        if result and result.get('id'):
            return jsonify({'ok': True, 'post_id': result['id']})
        err = (result or {}).get('error', {}).get('message', 'Lỗi không xác định')
        return jsonify({'ok': False, 'error': err})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/pages')
def api_pages():
    global _pages_cache
    try:
        pages = get_api(DEFAULT_GROUP).get_pages() or []
        _pages_cache = {p['id']: {'name': p['name'], 'access_token': p['access_token']} for p in pages}
        return jsonify([{'id': p['id'], 'name': p['name']} for p in pages])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/uploads/comment-image', methods=['POST'])
def upload_comment_image():
    file_storage = request.files.get('image')
    image_url, error = _upload_comment_image_to_supabase(file_storage)
    if not image_url:
        return jsonify({'ok': False, 'error': error or 'Upload ảnh thất bại'}), 400
    return jsonify({'ok': True, 'image_url': image_url})


@app.route('/api/comment', methods=['POST'])
def api_comment():
    body = request.get_json() or {}
    post_id = body.get('post_id', '').strip()
    message = body.get('message', '').strip()
    group_id = body.get('group_id', DEFAULT_GROUP)
    page_id = body.get('page_id', '').strip()
    post_url = body.get('post_url', '').strip()
    image_url = body.get('image_url', '').strip()
    if not post_id or (not message and not image_url):
        return jsonify({'ok': False, 'error': 'Thiếu post_id hoặc nội dung/ảnh bình luận'}), 400
    try:
        page_token = _page_token_from_cache(page_id) if page_id else None
        result = get_api(group_id).post_comment(post_id, message, page_token, image_url)
        if result and 'id' in result:
            log_text = message or '[Bình luận bằng ảnh]'
            log = _record_comment_log(post_id, group_id, post_url, log_text, page_id, 'success', comment_id=result['id'], image_url=image_url)
            payload = {'ok': True, 'comment_id': result['id'], 'log_storage': log.get('storage')}
            if log.get('storage_warning'):
                payload['warning'] = f"Đã lưu local, Supabase chưa ghi được: {log['storage_warning']}"
            return jsonify(payload)
        err = (result or {}).get('error', {}).get('message', 'Lỗi không xác định')
        log = _record_comment_log(post_id, group_id, post_url, message or '[Bình luận bằng ảnh]', page_id, 'failed', error_message=err, image_url=image_url)
        payload = {'ok': False, 'error': err, 'log_storage': log.get('storage')}
        if log.get('storage_warning'):
            payload['warning'] = f"Đã lưu local, Supabase chưa ghi được: {log['storage_warning']}"
        return jsonify(payload)
    except Exception as e:
        err = str(e)
        log = _record_comment_log(post_id, group_id, post_url, message or '[Bình luận bằng ảnh]', page_id, 'failed', error_message=err, image_url=image_url)
        payload = {'ok': False, 'error': err, 'log_storage': log.get('storage')}
        if log.get('storage_warning'):
            payload['warning'] = f"Đã lưu local, Supabase chưa ghi được: {log['storage_warning']}"
        return jsonify(payload), 500


@app.route('/api/comment-logs', methods=['GET'])
def comment_logs_get():
    if not _is_admin():
        staff_id = _current_staff_id()
        rows = [item for item in _comment_logs if item.get('staff_id') == staff_id]
    else:
        rows = _comment_logs
    return jsonify(rows[-200:])


@app.route('/api/comment-stats/today', methods=['GET'])
def comment_stats_today():
    staff_id = '' if _is_admin() else _current_staff_id()
    count, warning = _count_today_success_supabase(staff_id)
    storage = 'supabase'
    if count is None:
        count = _count_today_success_local(staff_id)
        storage = 'local'
    payload = {
        'ok': True,
        'success_count': count,
        'storage': storage,
        'scope': 'all' if _is_admin() else 'self',
    }
    if warning and storage == 'local':
        payload['warning'] = warning
    return jsonify(payload)


@app.route('/api/post-comments/fetch', methods=['POST'])
def fetch_facebook_post_comments():
    body = request.get_json() or {}
    post = body.get('post') or {}
    if not post or not post.get('id'):
        return jsonify({'ok': False, 'error': 'Thiếu bài viết Facebook'}), 400
    keywords = _normalize_keywords(body.get('keywords') or [])
    limit = max(1, min(int(body.get('limit') or 500), 1000))
    post_id = str(post.get('id'))
    page_id = str(post.get('_page_id') or body.get('page_id') or '').strip()
    group_id = str(post.get('_group_id') or page_id or DEFAULT_GROUP)
    try:
        if page_id:
            page_token = _page_token_from_cache(page_id)
            if not page_token:
                return jsonify({'ok': False, 'error': 'Không lấy được Page token. Kiểm tra quyền quản trị Page/cookie.'}), 502
            loaded = get_api(DEFAULT_GROUP).get_post_comments(post_id, limit=limit, access_token=page_token)
        else:
            loaded = get_api(group_id).get_post_comments(post_id, limit=limit)
        if loaded is None:
            return jsonify({'ok': False, 'error': 'Không đọc được bình luận Facebook. Kiểm tra cookie/quyền nhóm/Page.'}), 502
        comments = loaded.get('comments') or []
        total_count = int(loaded.get('total_count') or len(comments))
        fetched_at = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
        rows = _flatten_facebook_comment_rows(post, comments, keywords, fetched_at, _current_staff())
        storage, warning = _store_post_comment_rows(rows)
        matched_count = sum(1 for row in rows if row.get('is_matched'))
        payload = {
            'ok': True,
            'source': 'facebook',
            'post_id': post_id,
            'comment_count': total_count,
            'fetched_comment_count': len(rows),
            'matched_count': matched_count,
            'comments': rows,
            'storage': storage,
        }
        if warning:
            payload['warning'] = warning if storage == 'supabase' else f'Đã lưu local, Supabase chưa ghi được: {warning}'
        return jsonify(payload)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/tiktok/comments/fetch', methods=['POST'])
def fetch_tiktok_comments():
    body = request.get_json() or {}
    raw_url = str(body.get('url') or body.get('video_url') or body.get('video_id') or '').strip()
    keywords = _normalize_keywords(body.get('keywords') or [])
    limit = max(1, min(int(body.get('limit') or 300), 1000))
    cookie = str(body.get('cookie') or '').strip()
    channel_name = str(body.get('channel_name') or body.get('channel') or '').strip()
    video_title = str(body.get('video_title') or body.get('title') or '').strip()
    video_id, final_url = _extract_tiktok_video_id(raw_url)
    if not video_id:
        return jsonify({'ok': False, 'error': 'Không nhận diện được video TikTok. Dán link video hoặc ID video.'}), 400
    comments, fetch_error = _fetch_tiktok_comments(video_id, limit=limit, cookie=cookie)
    if not comments and fetch_error:
        return jsonify({'ok': False, 'error': fetch_error, 'source': 'tiktok', 'post_id': f'tiktok_{video_id}'}), 502
    fetched_at = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    rows = _flatten_tiktok_comment_rows(video_id, final_url, comments, keywords, fetched_at, _current_staff(), channel_name, video_title)
    storage, warning = _store_post_comment_rows(rows)
    matched_count = sum(1 for row in rows if row.get('is_matched'))
    phone_count = sum(1 for row in rows if extract_phones(row.get('message') or ''))
    payload = {
        'ok': True,
        'source': 'tiktok',
        'post_id': f'tiktok_{video_id}',
        'video_id': video_id,
        'post_url': final_url,
        'channel_name': channel_name or _derive_tiktok_channel_name(final_url),
        'video_title': video_title or f'Video {video_id}',
        'comment_count': len(rows),
        'fetched_comment_count': len(rows),
        'matched_count': matched_count,
        'phone_count': phone_count,
        'comments': rows,
        'storage': storage,
    }
    if fetch_error:
        payload['warning'] = fetch_error
    if warning:
        save_warning = warning if storage == 'supabase' else f'Đã lưu local, Supabase chưa ghi được: {warning}'
        payload['warning'] = (payload.get('warning') + ' | ' if payload.get('warning') else '') + save_warning
    return jsonify(payload)


@app.route('/api/tiktok/comment', methods=['POST'])
def send_tiktok_comment():
    body = request.get_json() or {}
    raw_url = str(body.get('url') or body.get('video_url') or body.get('post_url') or '').strip()
    raw_video_id = str(body.get('video_id') or '').strip()
    post_id = str(body.get('post_id') or '').strip()
    message = str(body.get('message') or body.get('text') or '').strip()
    cookie = str(body.get('cookie') or '').strip()
    if post_id.startswith('tiktok_') and not raw_video_id:
        raw_video_id = post_id.replace('tiktok_', '', 1)
    video_id, final_url = _extract_tiktok_video_id(raw_video_id or raw_url)
    if not video_id:
        return jsonify({'ok': False, 'error': 'Không nhận diện được video TikTok để bình luận.'}), 400
    if not message:
        return jsonify({'ok': False, 'error': 'Nhập nội dung bình luận TikTok'}), 400

    final_post_id = f'tiktok_{video_id}'
    if not final_url:
        final_url = raw_url or f'https://www.tiktok.com/@/video/{video_id}'
    payload, error = _send_tiktok_comment(video_id, final_url, message, cookie)
    if error:
        log = _record_comment_log(final_post_id, 'tiktok', final_url, message, 'tiktok', 'failed', error_message=error)
        res = {'ok': False, 'error': error, 'log_storage': log.get('storage')}
        if log.get('storage_warning'):
            res['warning'] = f"Đã lưu local, Supabase chưa ghi được: {log['storage_warning']}"
        return jsonify(res), 502

    comment_obj = payload.get('comment') if isinstance(payload.get('comment'), dict) else {}
    comment_id = str(
        comment_obj.get('cid')
        or comment_obj.get('id')
        or payload.get('cid')
        or payload.get('comment_id')
        or uuid.uuid4().hex
    )
    log = _record_comment_log(final_post_id, 'tiktok', final_url, message, 'tiktok', 'success', comment_id=f'tiktok_{comment_id}')
    staff = _current_staff()
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    rows = [{
        'source': 'tiktok',
        'post_id': final_post_id,
        'group_id': '',
        'post_url': final_url,
        'comment_id': f'tiktok_{comment_id}',
        'parent_comment_id': '',
        'depth': 0,
        'author_id': staff.get('id', ''),
        'author_name': staff.get('name') or staff.get('username') or 'Nhân sự',
        'message': message,
        'attachment_type': '',
        'created_time': now,
        'matched_keywords': [],
        'is_matched': False,
        'raw_comment': {
            'outbound': True,
            'publish_response': payload,
            '_video_meta': {
                'channel_name': _derive_tiktok_channel_name(final_url),
                'video_title': str(body.get('video_title') or f'Video {video_id}'),
                'video_id': video_id,
            },
        },
        'fetched_by_staff_id': staff.get('id', ''),
        'fetched_by_staff_name': staff.get('name', ''),
        'fetched_by_staff_username': staff.get('username', ''),
        'fetched_at': now,
    }]
    storage, storage_warning = _store_post_comment_rows(rows)
    res = {
        'ok': True,
        'source': 'tiktok',
        'post_id': final_post_id,
        'post_url': final_url,
        'comment_id': f'tiktok_{comment_id}',
        'storage': storage,
        'log_storage': log.get('storage'),
    }
    warnings = []
    if storage_warning:
        warnings.append(f'Comment đã gửi, nhưng Supabase post_comments chưa ghi được: {storage_warning}')
    if log.get('storage_warning'):
        warnings.append(f"Lịch sử comment đã lưu local, Supabase chưa ghi được: {log['storage_warning']}")
    if warnings:
        res['warning'] = ' | '.join(warnings)
    return jsonify(res)


@app.route('/api/tiktok/comment/result', methods=['POST'])
def record_tiktok_comment_result():
    body = request.get_json() or {}
    payload, status_code = _record_tiktok_extension_comment(body)
    return jsonify(payload), status_code


@app.route('/api/post-comments', methods=['GET'])
def list_post_comments():
    source = (request.args.get('source') or '').strip().lower()
    post_id = (request.args.get('post_id') or '').strip()
    keyword = (request.args.get('keyword') or '').strip().lower()
    limit = max(1, min(request.args.get('limit', 200, type=int), 1000))
    rows, warning = _load_post_comment_rows(source=source, post_id=post_id, limit=limit)
    if keyword:
        rows = [row for row in rows if keyword in str(row.get('message') or '').lower()]
    rows.sort(key=lambda row: row.get('created_time') or row.get('fetched_at') or '', reverse=True)
    payload = {'ok': True, 'count': len(rows[:limit]), 'comments': [_public_comment_row(row) for row in rows[:limit]]}
    if warning:
        payload['warning'] = warning
    return jsonify(payload)


@app.route('/api/tiktok/comment-stats', methods=['GET'])
def tiktok_comment_stats():
    limit = max(1, min(request.args.get('limit', 2000, type=int), 5000))
    rows, warning = _load_post_comment_rows(source='tiktok', limit=limit)
    stats = _tiktok_comment_stats(rows)
    payload = {
        'ok': True,
        'count': len(stats),
        'total_comments': sum(item.get('comment_count') or 0 for item in stats),
        'total_phone_comments': sum(item.get('phone_count') or 0 for item in stats),
        'stats': stats,
    }
    if warning:
        payload['warning'] = warning
    return jsonify(payload)


@app.route('/api/tiktok/config', methods=['GET'])
def tiktok_config_get():
    return jsonify({'ok': True, 'config': _public_tiktok_config()})


@app.route('/api/tiktok/config', methods=['POST'])
def tiktok_config_save():
    global _tiktok_config
    if not _is_admin():
        return jsonify({'ok': False, 'error': 'Chỉ admin được cập nhật TikTok cookie'}), 403
    body = request.get_json() or {}
    cookie = str(body.get('cookie') or '').strip()
    if not cookie:
        return jsonify({'ok': False, 'error': 'Dán cookie TikTok trước khi lưu'}), 400
    if '=' not in cookie:
        return jsonify({'ok': False, 'error': 'Cookie TikTok chưa đúng định dạng, cần chuỗi cookie đầy đủ từ trình duyệt'}), 400
    if not _has_tiktok_login_cookie(cookie):
        return jsonify({'ok': False, 'error': _tiktok_cookie_login_message(cookie)}), 400
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    staff = _current_staff()
    _tiktok_config = {
        **_default_tiktok_config(),
        **(_tiktok_config if isinstance(_tiktok_config, dict) else {}),
        'cookie': cookie,
        'updated_at': now,
        'updated_by': staff.get('name') or staff.get('username') or '',
    }
    _save_tiktok_config()
    return jsonify({'ok': True, 'config': _public_tiktok_config(), 'storage': 'supabase' if USE_SUPABASE else 'local'})


@app.route('/api/tiktok/config/test', methods=['POST'])
def tiktok_config_test():
    body = request.get_json() or {}
    cookie = str(body.get('cookie') or '').strip() or _configured_tiktok_cookie()
    has_login_cookie = _has_tiktok_login_cookie(cookie)
    return jsonify({
        'ok': True,
        'valid': bool(cookie and has_login_cookie),
        'has_cookie': bool(cookie),
        'has_login_cookie': has_login_cookie,
        'message': _tiktok_cookie_login_message(cookie),
        'config': _public_tiktok_config(),
    })


@app.route('/api/tiktok/config', methods=['DELETE'])
def tiktok_config_delete():
    global _tiktok_config
    if not _is_admin():
        return jsonify({'ok': False, 'error': 'Chỉ admin được xoá TikTok cookie'}), 403
    _tiktok_config = {**_default_tiktok_config(), 'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z'}
    _save_tiktok_config()
    return jsonify({'ok': True, 'config': _public_tiktok_config(), 'storage': 'supabase' if USE_SUPABASE else 'local'})


@app.route('/api/groups/resolve')
def api_resolve_group():
    slug = request.args.get('slug', '').strip()
    if not slug:
        return jsonify({'ok': False, 'error': 'Thiếu slug'}), 400
    try:
        api = get_api(DEFAULT_GROUP)
        data = api.resolve_slug(slug)
        if data and 'id' in data:
            is_member = api.check_membership(data['id'])
            return jsonify({'ok': True, 'id': data['id'], 'name': data.get('name', slug), 'is_member': is_member})
        if data is None and not api.access_token:
            return jsonify({
                'ok': False,
                'error': 'Cookie/token Facebook hết hạn hoặc tài khoản đang đăng nhập chưa có cookie. Vào Nhân sự/Cooki, cập nhật cookie cho đúng tài khoản đang dùng rồi bấm Tải lại.',
            }), 401
        err = (data or {}).get('error', {}).get('message', 'Không tìm thấy group')
        return jsonify({'ok': False, 'error': err})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/groups/<gid>/join', methods=['POST'])
def api_join_group(gid):
    try:
        result = get_api(DEFAULT_GROUP).join_group(gid)
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


def _sync_group_from_channel(row: dict) -> None:
    global _groups
    platform = str(row.get('platform') or '').strip().lower()
    channel_type = str(row.get('channel_type') or '').strip().lower()
    target_id = str(row.get('target_id') or '').strip()
    if platform != 'facebook' or channel_type not in ('nhóm', 'nhom', 'group') or not _is_valid_facebook_numeric_id(target_id):
        return
    name = str(row.get('channel_name') or '').strip()
    if not any(g.get('id') == target_id for g in _groups):
        _groups.append({'id': target_id, 'name': name})
    else:
        for group in _groups:
            if group.get('id') == target_id and name:
                group['name'] = name
    _save_groups()
    if USE_SUPABASE:
        try:
            sb.upsert_group(target_id, name)
        except Exception as e:
            print(f'[supabase] upsert_group from managed channel failed: {e}')


def _facebook_group_channels() -> list[dict]:
    global _managed_channels
    rows = []
    changed = False
    next_channels = []
    for row in _managed_channels:
        original_target = str(row.get('target_id') or '').strip()
        row = _resolve_facebook_group_channel(row)
        if str(row.get('target_id') or '').strip() != original_target:
            changed = True
        next_channels.append(row)
        platform = str(row.get('platform') or '').strip().lower()
        channel_type = str(row.get('channel_type') or '').strip().lower()
        target_id = str(row.get('target_id') or '').strip()
        if platform == 'facebook' and channel_type in ('nhóm', 'nhom', 'group') and _is_valid_facebook_numeric_id(target_id):
            rows.append({'id': target_id, 'name': str(row.get('channel_name') or '').strip()})
    if changed:
        _managed_channels = next_channels
        _save_managed_channels()
    return rows


def _merged_facebook_groups() -> list[dict]:
    by_id = {}
    for row in _groups:
        gid = str(row.get('id') or '').strip()
        if _is_valid_facebook_numeric_id(gid):
            by_id[gid] = {'id': gid, 'name': str(row.get('name') or '').strip()}
    for row in _facebook_group_channels():
        gid = row['id']
        if gid not in by_id:
            by_id[gid] = row
        elif row.get('name'):
            by_id[gid]['name'] = row['name']
    return list(by_id.values())


def _refresh_managed_channels_from_supabase() -> None:
    global _managed_channels
    if not USE_SUPABASE:
        return
    try:
        rows = sb.list_managed_channels(SUPABASE_CHANNEL_TABLE)
        if isinstance(rows, list):
            _managed_channels = rows
    except Exception as e:
        print(f'[supabase] refresh managed_channels failed: {e}')


@app.route('/api/channels', methods=['GET'])
def channels_get():
    _refresh_managed_channels_from_supabase()
    rows = [_public_managed_channel(item) for item in _managed_channels]
    rows.sort(key=lambda item: item.get('created_at') or item.get('updated_at') or '', reverse=True)
    return jsonify({'ok': True, 'channels': rows})


@app.route('/api/channels', methods=['POST'])
def channels_create():
    global _managed_channels
    body = request.get_json() or {}
    row = _clean_managed_channel(body)
    row = _resolve_facebook_group_channel(row)
    validation_error = _facebook_channel_validation_error(row)
    if validation_error:
        return jsonify({'ok': False, 'error': validation_error}), 400
    if not row['platform']:
        return jsonify({'ok': False, 'error': 'Thiếu nền tảng'}), 400
    if not row['channel_name']:
        return jsonify({'ok': False, 'error': 'Thiếu tên kênh'}), 400
    if not row['target_id'] and not row['link']:
        return jsonify({'ok': False, 'error': 'Thiếu link hoặc ID'}), 400
    duplicated = _find_duplicate_managed_channel(row)
    if duplicated:
        return jsonify({
            'ok': False,
            'error': f"Kênh này đã có trong danh sách: {duplicated.get('channel_name') or duplicated.get('target_id') or duplicated.get('id')}",
            'duplicate': _public_managed_channel(duplicated),
        }), 409
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    row = {
        'id': uuid.uuid4().hex[:12],
        **row,
        'created_at': now,
        'updated_at': now,
    }
    if USE_SUPABASE:
        try:
            row = {**row, **sb.upsert_managed_channel(row, SUPABASE_CHANNEL_TABLE)}
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Không lưu được kênh lên Supabase: {_managed_channel_store_error(e)}'}), 500
    _managed_channels = [item for item in _managed_channels if item.get('id') != row['id']]
    _managed_channels.append(row)
    _save_managed_channels()
    _sync_group_from_channel(row)
    return jsonify({'ok': True, 'channel': _public_managed_channel(row), 'channels': [_public_managed_channel(item) for item in _managed_channels]})


@app.route('/api/channels/<channel_id>', methods=['PUT'])
def channels_update(channel_id):
    global _managed_channels
    current = next((item for item in _managed_channels if item.get('id') == channel_id), {})
    if not current and USE_SUPABASE:
        try:
            remote = sb.list_managed_channels(SUPABASE_CHANNEL_TABLE)
            current = next((item for item in remote if item.get('id') == channel_id), {})
        except Exception:
            current = {}
    if not current:
        return jsonify({'ok': False, 'error': 'Không tìm thấy kênh'}), 404
    body = request.get_json() or {}
    row = {**current, **_clean_managed_channel(body, current), 'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z'}
    row = _resolve_facebook_group_channel(row)
    validation_error = _facebook_channel_validation_error(row)
    if validation_error:
        return jsonify({'ok': False, 'error': validation_error}), 400
    if not row.get('platform') or not row.get('channel_name'):
        return jsonify({'ok': False, 'error': 'Thiếu nền tảng hoặc tên kênh'}), 400
    if not row.get('target_id') and not row.get('link'):
        return jsonify({'ok': False, 'error': 'Thiếu link hoặc ID'}), 400
    duplicated = _find_duplicate_managed_channel(row, exclude_id=channel_id)
    if duplicated:
        return jsonify({
            'ok': False,
            'error': f"Kênh này đã có trong danh sách: {duplicated.get('channel_name') or duplicated.get('target_id') or duplicated.get('id')}",
            'duplicate': _public_managed_channel(duplicated),
        }), 409
    if USE_SUPABASE:
        try:
            row = {**row, **sb.update_managed_channel(channel_id, row, SUPABASE_CHANNEL_TABLE)}
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Không cập nhật được kênh trên Supabase: {_managed_channel_store_error(e)}'}), 500
    _managed_channels = [row if item.get('id') == channel_id else item for item in _managed_channels]
    if not any(item.get('id') == channel_id for item in _managed_channels):
        _managed_channels.append(row)
    _save_managed_channels()
    _sync_group_from_channel(row)
    return jsonify({'ok': True, 'channel': _public_managed_channel(row), 'channels': [_public_managed_channel(item) for item in _managed_channels]})


@app.route('/api/channels/<channel_id>', methods=['DELETE'])
def channels_delete(channel_id):
    global _managed_channels
    if USE_SUPABASE:
        try:
            sb.delete_managed_channel(channel_id, SUPABASE_CHANNEL_TABLE)
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Không xoá được kênh trên Supabase: {_managed_channel_store_error(e)}'}), 500
    _managed_channels = [item for item in _managed_channels if item.get('id') != channel_id]
    _save_managed_channels()
    return jsonify({'ok': True, 'channels': [_public_managed_channel(item) for item in _managed_channels]})


@app.route('/api/telegram/chatids', methods=['GET'])
def tg_get():
    return jsonify(_tg_chat_ids)


@app.route('/api/telegram/chatids', methods=['POST'])
def tg_add():
    cid = (request.get_json() or {}).get('chat_id', '').strip()
    if not cid:
        return jsonify({'ok': False, 'error': 'Thiếu chat_id'}), 400
    if cid not in _tg_chat_ids:
        _tg_chat_ids.append(cid)
        _save_tg()
        if USE_SUPABASE:
            try:
                sb.add_chat_id(cid)
            except Exception as e:
                print(f'[supabase] add_chat_id failed: {e}')
    return jsonify({'ok': True, 'chat_ids': _tg_chat_ids})


@app.route('/api/telegram/chatids/<chat_id>', methods=['DELETE'])
def tg_remove(chat_id):
    if chat_id in _tg_chat_ids:
        _tg_chat_ids.remove(chat_id)
        _save_tg()
        if USE_SUPABASE:
            try:
                sb.remove_chat_id(chat_id)
            except Exception as e:
                print(f'[supabase] remove_chat_id failed: {e}')
    return jsonify({'ok': True, 'chat_ids': _tg_chat_ids})


@app.route('/api/groups', methods=['GET'])
def groups_get():
    _refresh_managed_channels_from_supabase()
    return jsonify(_merged_facebook_groups())


@app.route('/api/groups', methods=['POST'])
def groups_add():
    global _groups
    body = request.get_json() or {}
    gid = body.get('id', '').strip()
    name = body.get('name', '').strip()
    if not gid:
        return jsonify({'ok': False, 'error': 'Thiếu id'}), 400
    if not _is_valid_facebook_numeric_id(gid):
        return jsonify({
            'ok': False,
            'error': 'ID nhóm Facebook chưa hợp lệ. Hãy nhập link nhóm dạng facebook.com/groups/<ID số> hoặc ID nhóm thật 10-20 chữ số.',
        }), 400
    if not any(g['id'] == gid for g in _groups):
        _groups.append({'id': gid, 'name': name})
    else:
        for g in _groups:
            if g['id'] == gid and name:
                g['name'] = name
    _save_groups()
    if USE_SUPABASE:
        try:
            sb.upsert_group(gid, name)
        except Exception as e:
            print(f'[supabase] upsert_group failed: {e}')
    return jsonify({'ok': True, 'groups': _groups})


@app.route('/api/groups/<gid>', methods=['DELETE'])
def groups_remove(gid):
    global _groups
    _groups = [g for g in _groups if g['id'] != gid]
    _save_groups()
    if USE_SUPABASE:
        try:
            sb.delete_group(gid)
        except Exception as e:
            print(f'[supabase] delete_group failed: {e}')
    return jsonify({'ok': True, 'groups': _groups})


@app.route('/api/staff-cookies', methods=['GET'])
def staff_cookies_get():
    warning = ''
    if _is_admin():
        staff_rows, warning = _merged_public_staff_rows()
    else:
        staff_rows = [_public_current_staff()] if _current_staff() else []
    payload = {
        'active_staff_id': _current_staff_id(),
        'staff': staff_rows,
        'can_manage': _is_admin(),
        'fallback_cookie': bool(load_cookie()),
    }
    if warning:
        payload['warning'] = warning
    return jsonify(payload)


@app.route('/api/staff-cookies', methods=['POST'])
def staff_cookies_save():
    global _staff_cookies
    if not _is_admin():
        return jsonify({'ok': False, 'error': 'Chỉ admin được thêm nhân sự'}), 403
    body = request.get_json() or {}
    name = str(body.get('name') or '').strip()[:80]
    username = str(body.get('username') or '').strip().lower()[:60]
    password = str(body.get('password') or '')
    cookie = str(body.get('cookie') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Thiếu tên nhân sự'}), 400
    if not username:
        return jsonify({'ok': False, 'error': 'Thiếu tài khoản đăng nhập'}), 400
    if len(password) < 6:
        return jsonify({'ok': False, 'error': 'Mật khẩu tối thiểu 6 ký tự'}), 400
    if not cookie:
        return jsonify({'ok': False, 'error': 'Thiếu cookie'}), 400
    if 'c_user=' not in cookie:
        return jsonify({'ok': False, 'error': 'Cookie chưa có c_user, vui lòng kiểm tra lại'}), 400

    staff = _staff_cookies.setdefault('staff', [])
    if any(item.get('username') == username for item in staff):
        return jsonify({'ok': False, 'error': 'Tài khoản đăng nhập đã tồn tại'}), 400
    if USE_SUPABASE:
        existing_row, existing_error = _load_supabase_staff(username)
        if existing_row and _as_enabled(existing_row.get('enabled', True)):
            return jsonify({'ok': False, 'error': 'Tài khoản đăng nhập đã tồn tại trong Supabase'}), 400
        if existing_error and 'Could not find the table' in existing_error:
            return jsonify({'ok': False, 'error': f'Chưa có bảng {SUPABASE_STAFF_TABLE} trong Supabase'}), 500
    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    saved_id = uuid.uuid4().hex[:12]
    salt, digest = _hash_password(password)
    remote_row = {
        'id': saved_id,
        'name': name,
        'username': username,
        'password': password,
        'role': 'staff',
        'cookie': cookie,
        'facebook_user_id': _extract_cookie_user(cookie),
        'enabled': True,
    }
    if USE_SUPABASE:
        try:
            if existing_row and not _as_enabled(existing_row.get('enabled', True)):
                remote_row['id'] = existing_row.get('id') or saved_id
                sb.update_staff_user(username, remote_row, SUPABASE_STAFF_TABLE)
                saved_id = remote_row['id']
            else:
                sb.insert_staff_user(remote_row, SUPABASE_STAFF_TABLE)
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Không lưu được nhân sự lên Supabase: {e}'}), 500

    local_row = {
        'id': saved_id,
        'name': name,
        'username': username,
        'password_salt': salt,
        'password_hash': digest,
        'cookie': cookie,
        'role': 'staff',
        'enabled': True,
        'created_at': now,
        'updated_at': now,
    }
    staff.append(local_row)
    if not _staff_cookies.get('active_staff_id'):
        _staff_cookies['active_staff_id'] = saved_id
    _save_staff_cookies()
    _invalidate_facebook_cache()
    staff_rows, warning = _merged_public_staff_rows()
    return jsonify({
        'ok': True,
        'active_staff_id': _current_staff_id(),
        'staff': staff_rows,
        'can_manage': True,
        'storage': 'supabase' if USE_SUPABASE else 'local',
        'warning': warning,
    })


@app.route('/api/staff-cookies/<staff_id>', methods=['PUT', 'PATCH'])
def staff_cookies_update(staff_id):
    if not _is_admin():
        return jsonify({'ok': False, 'error': 'Chỉ admin được sửa nhân sự'}), 403

    body = request.get_json() or {}
    staff = _staff_accounts()
    local_target = next((item for item in staff if item.get('id') == staff_id), {})
    remote_target = {}
    remote_warning = ''
    if USE_SUPABASE:
        remote_rows, remote_warning = _list_supabase_staff()
        remote_target = next((item for item in remote_rows if item.get('id') == staff_id), {})

    # Supabase is the source of truth in production. Local JSON can be stale
    # after deploys, so let remote values win when both records exist.
    target = {**local_target, **remote_target}
    if not target:
        return jsonify({'ok': False, 'error': 'Không tìm thấy nhân sự'}), 404

    name = str(body.get('name', target.get('name', '')) or '').strip()[:80]
    username = str(body.get('username', target.get('username', '')) or '').strip().lower()[:60]
    password = str(body.get('password') or '')
    cookie = str(body.get('cookie') or '').strip()

    if not name:
        return jsonify({'ok': False, 'error': 'Thiếu tên nhân sự'}), 400
    if not username:
        return jsonify({'ok': False, 'error': 'Thiếu tài khoản đăng nhập'}), 400
    if password and len(password) < 6:
        return jsonify({'ok': False, 'error': 'Mật khẩu tối thiểu 6 ký tự'}), 400
    if cookie and 'c_user=' not in cookie:
        return jsonify({'ok': False, 'error': 'Cookie chưa có c_user, vui lòng kiểm tra lại'}), 400

    for item in staff:
        if item.get('id') != staff_id and item.get('username') == username and _as_enabled(item.get('enabled', True)):
            return jsonify({'ok': False, 'error': 'Tài khoản đăng nhập đã tồn tại'}), 400
    if USE_SUPABASE:
        existing_row, existing_error = _load_supabase_staff(username)
        if existing_row and str(existing_row.get('id') or '') != staff_id and _as_enabled(existing_row.get('enabled', True)):
            return jsonify({'ok': False, 'error': 'Tài khoản đăng nhập đã tồn tại trong Supabase'}), 400
        if existing_error and 'Could not find the table' in existing_error:
            return jsonify({'ok': False, 'error': f'Chưa có bảng {SUPABASE_STAFF_TABLE} trong Supabase'}), 500

    now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    remote_row = {
        'name': name,
        'username': username,
        'role': target.get('role') or 'staff',
        'enabled': True,
        'updated_at': now,
    }
    if password:
        remote_row['password'] = password
    if cookie:
        remote_row['cookie'] = cookie
        remote_row['facebook_user_id'] = _extract_cookie_user(cookie)

    if USE_SUPABASE:
        try:
            sb.update_staff_user_by_id(staff_id, remote_row, SUPABASE_STAFF_TABLE)
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Không cập nhật được nhân sự trên Supabase: {e}'}), 500

    if local_target:
        local_target['name'] = name
        local_target['username'] = username
        local_target['role'] = target.get('role') or local_target.get('role') or 'staff'
        local_target['updated_at'] = now
        if password:
            salt, digest = _hash_password(password)
            local_target['password_salt'] = salt
            local_target['password_hash'] = digest
        if cookie:
            local_target['cookie'] = cookie
            local_target['facebook_user_id'] = _extract_cookie_user(cookie)
    else:
        local_row = {
            'id': staff_id,
            'name': name,
            'username': username,
            'role': target.get('role') or 'staff',
            'enabled': True,
            'created_at': target.get('created_at') or now,
            'updated_at': now,
        }
        if password:
            salt, digest = _hash_password(password)
            local_row['password_salt'] = salt
            local_row['password_hash'] = digest
        if cookie:
            local_row['cookie'] = cookie
            local_row['facebook_user_id'] = _extract_cookie_user(cookie)
        staff.append(local_row)

    if cookie:
        _remove_staff_token_file(staff_id)

    _save_staff_cookies()
    _invalidate_facebook_cache()
    refreshed_staff = {
        **target,
        **remote_row,
        'id': staff_id,
        'cookie': cookie or target.get('cookie', ''),
        'facebook_user_id': remote_row.get('facebook_user_id') or target.get('facebook_user_id', ''),
    }
    _refresh_staff_session_cache(staff_id, refreshed_staff)
    staff_rows, warning = _merged_public_staff_rows()
    if remote_warning and not warning:
        warning = remote_warning
    return jsonify({
        'ok': True,
        'active_staff_id': _current_staff_id(),
        'staff': staff_rows,
        'can_manage': True,
        'storage': 'supabase' if USE_SUPABASE else 'local',
        'warning': warning,
    })


@app.route('/api/staff-cookies/<staff_id>/activate', methods=['POST'])
def staff_cookies_activate(staff_id):
    return jsonify({'ok': False, 'error': 'Cookie được gắn theo tài khoản đăng nhập, không cho chọn thủ công'}), 403


@app.route('/api/staff-cookies/<staff_id>', methods=['DELETE'])
def staff_cookies_delete(staff_id):
    if not _is_admin():
        return jsonify({'ok': False, 'error': 'Chỉ admin được xoá nhân sự'}), 403
    if staff_id == _current_staff_id():
        return jsonify({'ok': False, 'error': 'Không thể xoá tài khoản đang đăng nhập'}), 400
    staff = _staff_accounts()
    target = next((item for item in staff if item.get('id') == staff_id), {})
    if USE_SUPABASE:
        try:
            sb.delete_staff_user(staff_id=staff_id, username=target.get('username', ''), table=SUPABASE_STAFF_TABLE)
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Không xoá được nhân sự trên Supabase: {e}'}), 500
    _staff_cookies['staff'] = [item for item in staff if item.get('id') != staff_id]
    if _staff_cookies.get('active_staff_id') == staff_id:
        _staff_cookies['active_staff_id'] = (_staff_cookies['staff'][0]['id'] if _staff_cookies['staff'] else '')
    try:
        os.remove(_staff_token_file(staff_id))
    except OSError:
        pass
    _save_staff_cookies()
    _invalidate_facebook_cache()
    staff_rows, warning = _merged_public_staff_rows()
    return jsonify({'ok': True, 'active_staff_id': _current_staff_id(), 'staff': staff_rows, 'can_manage': True, 'warning': warning})


@app.route('/api/settings', methods=['GET'])
def settings_get():
    defaults = {
        'auto_refresh': True,
        'interval': 5,
        'auto_assign_sale': True,
        'notify_hot_lead': True,
        'sla_monitor': True,
        'auto_comment_hot': False,
        'auto_comment_max_per_hour': 8,
        'server_auto_scan': False,
        'scan_interval_min': 5,
    }
    merged = {**defaults, **(_settings or {})}
    merged['last_auto_scan_at'] = _last_auto_scan_at.get('value') or ''
    merged['scanned_today'] = _count_scanned_today()
    return jsonify(merged)


@app.route('/api/settings', methods=['POST'])
def settings_save():
    global _settings
    body = request.get_json() or {}
    allowed_keys = ('auto_refresh', 'interval', 'auto_assign_sale', 'notify_hot_lead', 'sla_monitor', 'auto_comment_hot', 'auto_comment_max_per_hour', 'server_auto_scan', 'scan_interval_min')
    _settings.update({k: v for k, v in body.items() if k in allowed_keys})
    _save_settings()
    return jsonify({'ok': True, 'settings': _settings})


@app.route('/api/automation/run-once', methods=['POST'])
def automation_run_once():
    """Chạy thử một vòng quét ngay để kiểm tra cấu hình trước khi bật nền."""
    try:
        result = _auto_scan_tick() or {'ok': True, 'message': 'Đã chạy xong.', 'post_count': 0, 'lead_count': 0}
        result['scanned_today'] = _count_scanned_today()
        result['last_auto_scan_at'] = _last_auto_scan_at.get('value') or result.get('last_auto_scan_at') or ''
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/business-profile', methods=['GET'])
def business_profile_get():
    global _business_profile
    try:
        storage = 'local'
        warning = ''
        if not any((_business_profile or {}).values()):
            remote_profile, warning = _load_business_profile_from_supabase()
            if remote_profile:
                _business_profile = {**_default_business_profile(), **remote_profile}
                _save_business_profile()
                storage = 'supabase'
        payload = {'ok': True, 'profile': _business_profile, 'storage': storage}
        if warning:
            payload['warning'] = warning
        return jsonify(payload)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/business-profile', methods=['POST'])
def business_profile_save():
    global _business_profile
    try:
        body = request.get_json() or {}
        _business_profile = _clean_business_profile(body)
        _save_business_profile()

        supabase_ok, supabase_error = _save_business_profile_to_supabase(_business_profile)
        storage = 'supabase' if supabase_ok else 'local'
        payload = {'ok': True, 'profile': _business_profile, 'storage': storage}
        if supabase_error:
            payload['warning'] = f'Đã lưu local, Supabase chưa ghi được: {supabase_error}'
        return jsonify(payload)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/business-profile/generate-text', methods=['POST'])
def business_profile_generate_text():
    global _business_profile
    try:
        body = request.get_json() or {}
        profile = _clean_business_profile(body)
        if not any(profile.values()):
            return jsonify({'ok': False, 'error': 'Nhập ít nhất một thông tin trước khi tạo văn bản'}), 400

        classifier = _get_classifier()
        if not classifier.api_key:
            return jsonify({'ok': False, 'error': 'Chưa cấu hình API key — thêm GEMINI_API_KEY vào .env hoặc key trong UI'}), 400

        generated = classifier.generate_business_text(profile)
        if classifier.last_error and not generated:
            return jsonify({'ok': False, 'error': classifier.last_error}), 502
        if not generated:
            return jsonify({'ok': False, 'error': 'AI chưa tạo được văn bản phù hợp'}), 502

        _business_profile = _clean_business_profile(generated)
        _save_business_profile()

        supabase_ok, supabase_error = _save_business_profile_to_supabase(_business_profile)
        storage = 'supabase' if supabase_ok else 'local'
        payload = {'ok': True, 'profile': _business_profile, 'storage': storage}
        if supabase_error:
            payload['warning'] = f'Đã lưu local, Supabase chưa ghi được: {supabase_error}'
        return jsonify(payload)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/telegram/test/<chat_id>', methods=['POST'])
def tg_test(chat_id):
    try:
        r = _req.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': chat_id, 'text': '✅ Kết nối Telegram thành công!'},
            timeout=10,
        )
        return jsonify({'ok': r.ok})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── AI Routes ──────────────────────────────────────────
@app.route('/api/ai/providers')
def ai_providers():
    return jsonify(PROVIDERS)


@app.route('/api/ai/config', methods=['GET'])
def ai_config_get():
    safe = dict(_ai_config)
    safe_keys = {}
    for k, v in safe.get('keys', {}).items():
        safe_keys[k] = ('***' + v[-4:]) if v and len(v) > 4 else ('***' if v else '')
    safe.pop('keys', None)
    safe['keys_masked'] = safe_keys
    return jsonify(safe)


@app.route('/api/ai/config', methods=['POST'])
def ai_config_save():
    global _ai_config
    body = request.get_json() or {}
    if 'provider' in body:
        _ai_config['provider'] = body['provider']
    if 'model' in body:
        _ai_config['model'] = body['model']
    if 'auto_classify' in body:
        _ai_config['auto_classify'] = bool(body['auto_classify'])
    if 'categories' in body and isinstance(body['categories'], list):
        _ai_config['categories'] = body['categories']
    if 'key' in body:
        provider = body.get('provider', _ai_config.get('provider', 'gemini'))
        if 'keys' not in _ai_config:
            _ai_config['keys'] = {}
        _ai_config['keys'][provider] = body['key']
    _save_ai_config()
    return jsonify({'ok': True})


@app.route('/api/ai/test', methods=['POST'])
def ai_test():
    classifier = _get_classifier()
    if not classifier.api_key:
        return jsonify({'ok': False, 'error': 'Chưa nhập API key'})
    result = classifier.test_connection()
    return jsonify(result)


@app.route('/api/ai/key/<provider>', methods=['DELETE'])
def ai_key_delete(provider):
    global _ai_config
    if 'keys' in _ai_config and provider in _ai_config['keys']:
        _ai_config['keys'][provider] = ''
        _save_ai_config()
    return jsonify({'ok': True})


@app.route('/api/ai/classify', methods=['POST'])
def ai_classify():
    global _classifications
    body = request.get_json() or {}
    posts = body.get('posts', [])
    force = body.get('force', False)
    if not posts:
        return jsonify({'ok': False, 'error': 'Không có bài viết'})
    classifier = _get_classifier()
    if not classifier.api_key:
        return jsonify({'ok': False, 'error': 'Chưa cấu hình API key'})
    to_classify = [p for p in posts if force or p.get('id') not in _classifications]
    if not to_classify:
        return jsonify({'ok': True, 'classifications': {pid: _classifications[pid] for pid in [p['id'] for p in posts] if pid in _classifications}})
    results = classifier.classify_posts(to_classify)
    if classifier.last_error and not results:
        return jsonify({'ok': False, 'error': classifier.last_error}), 502
    _classifications.update(results)
    _save_classifications(results)
    all_results = {p['id']: _classifications.get(p['id'], '') for p in posts}
    return jsonify({'ok': True, 'classifications': all_results})


@app.route('/api/ai/classifications', methods=['GET'])
def ai_classifications_get():
    return jsonify(_classifications)


@app.route('/api/ai/leads', methods=['GET'])
def ai_leads_get():
    remote, warning = _load_leads_from_supabase()
    if remote:
        merged = {**_leads}
        for post_id, items in remote.items():
            merged_items = merged.setdefault(post_id, [])
            by_key = {str(item.get('lead_key') or _lead_key(item)): item for item in merged_items}
            for item in items:
                by_key[str(item.get('lead_key') or _lead_key(item))] = item
            merged[post_id] = list(by_key.values())
        return jsonify(merged)
    return jsonify(_leads)


@app.route('/api/leads/dashboard', methods=['GET'])
def leads_dashboard_get():
    remote, warning = _load_leads_from_supabase()
    grouped = remote or _leads
    payload = {'ok': True, 'dashboard': _lead_dashboard_payload(grouped)}
    if warning and not remote:
        payload['warning'] = warning
    return jsonify(payload)


@app.route('/api/leads/<lead_key>', methods=['PATCH'])
def lead_update(lead_key):
    body = request.get_json() or {}
    allowed = {
        'lead_status', 'assigned_sale_id', 'assigned_sale_name', 'next_action',
        'contact_status', 'urgency', 'budget', 'location', 'product_or_service',
    }
    patch = {key: body.get(key) for key in allowed if key in body}
    if not patch:
        return jsonify({'ok': False, 'error': 'Không có dữ liệu cập nhật'}), 400

    remote, _warning = _load_leads_from_supabase()
    found = False
    updated = {}
    source_lead = {}
    for item in _flatten_lead_groups(remote or _leads):
        if str(item.get('lead_key') or '') == str(lead_key):
            source_lead = item
            break

    # Ghi timeline nếu trạng thái thay đổi (đặc tả Bước 7)
    if 'lead_status' in patch and source_lead:
        old_status = str(source_lead.get('lead_status') or 'new')
        new_status = str(patch.get('lead_status') or 'new')
        if new_status != old_status:
            staff = _current_staff()
            history = _append_status_history(
                source_lead,
                new_status,
                note=str(body.get('note') or ''),
                by=staff.get('name', ''),
            )
            patch['status_history'] = history

    if source_lead:
        updated = _normalise_lead({**source_lead, **patch, 'lead_key': lead_key, 'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z'}, source_lead.get('post_id') or '')
        found = True

    if not found:
        found, updated = _update_lead_in_memory(str(lead_key), patch)
    else:
        _update_lead_in_memory(str(lead_key), patch)
    if not found:
        return jsonify({'ok': False, 'error': 'Không tìm thấy lead'}), 404

    supabase_ok, supabase_error = _patch_lead_in_supabase(str(lead_key), updated)
    payload = {'ok': True, 'lead': updated, 'storage': 'supabase' if supabase_ok else 'local'}
    if supabase_error:
        payload['warning'] = supabase_error
    return jsonify(payload)


@app.route('/api/leads/<lead_key>/event', methods=['POST'])
def lead_add_event(lead_key):
    """Ghi nhận hành vi khách (comment/inbox/demo/từ chối/spam...) để tính điểm động (đặc tả Mục III)."""
    body = request.get_json() or {}
    event_type = str(body.get('event') or body.get('type') or '').strip()
    if event_type not in BEHAVIOR_SCORE_RULES:
        valid = ', '.join(BEHAVIOR_SCORE_RULES.keys())
        return jsonify({'ok': False, 'error': f'Sự kiện không hợp lệ. Hợp lệ: {valid}'}), 400

    remote, _warning = _load_leads_from_supabase()
    source_lead = {}
    for item in _flatten_lead_groups(remote or _leads):
        if str(item.get('lead_key') or '') == str(lead_key):
            source_lead = item
            break
    if not source_lead:
        return jsonify({'ok': False, 'error': 'Không tìm thấy lead'}), 404

    staff = _current_staff()
    events = source_lead.get('behavior_events') if isinstance(source_lead.get('behavior_events'), list) else []
    events = [*events, {
        'type': event_type,
        'note': str(body.get('note') or ''),
        'by': staff.get('name', ''),
        'at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
    }]
    prev_level = str(source_lead.get('lead_level') or '')
    updated = _normalise_lead({**source_lead, 'behavior_events': events, 'lead_key': lead_key, 'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z'}, source_lead.get('post_id') or '')
    _update_lead_in_memory(str(lead_key), {'behavior_events': events})
    supabase_ok, supabase_error = _patch_lead_in_supabase(str(lead_key), updated)

    # Nếu vừa lên nóng/rất nóng thì thông báo
    if updated.get('lead_level') in ('hot', 'very_hot') and updated.get('lead_level') != prev_level:
        threading.Thread(target=_notify_hot_lead, args=(updated,), daemon=True).start()

    payload = {'ok': True, 'lead': updated, 'storage': 'supabase' if supabase_ok else 'local'}
    if supabase_error:
        payload['warning'] = supabase_error
    return jsonify(payload)


@app.route('/api/sales/roster', methods=['GET'])
def sales_roster_get():
    """Danh sách sale có thể nhận lead (phục vụ chia lead)."""
    return jsonify({'ok': True, 'sales': _sale_roster()})


@app.route('/api/leads/<lead_key>/assign', methods=['POST'])
def lead_assign(lead_key):
    """Chia lead cho sale: nếu không truyền sale_id thì tự động round-robin."""
    body = request.get_json() or {}
    remote, _warning = _load_leads_from_supabase()
    source_lead = {}
    for item in _flatten_lead_groups(remote or _leads):
        if str(item.get('lead_key') or '') == str(lead_key):
            source_lead = item
            break
    if not source_lead:
        return jsonify({'ok': False, 'error': 'Không tìm thấy lead'}), 404

    sale_id = str(body.get('sale_id') or '').strip()
    if sale_id:
        sale = next((s for s in _sale_roster() if s['id'] == sale_id), None)
        if not sale:
            return jsonify({'ok': False, 'error': 'Không tìm thấy sale'}), 404
        source_lead['assigned_sale_id'] = sale['id']
        source_lead['assigned_sale_name'] = sale['name']
    else:
        source_lead.pop('assigned_sale_id', None)
        source_lead.pop('assigned_sale_name', None)
        _auto_assign_sale(source_lead)

    updated = _normalise_lead({**source_lead, 'lead_key': lead_key, 'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z'}, source_lead.get('post_id') or '')
    _update_lead_in_memory(str(lead_key), {
        'assigned_sale_id': updated.get('assigned_sale_id'),
        'assigned_sale_name': updated.get('assigned_sale_name'),
    })
    supabase_ok, supabase_error = _patch_lead_in_supabase(str(lead_key), updated)
    payload = {'ok': True, 'lead': updated, 'storage': 'supabase' if supabase_ok else 'local'}
    if supabase_error:
        payload['warning'] = supabase_error
    return jsonify(payload)


@app.route('/api/leads/<lead_key>/auto-comment', methods=['POST'])
def lead_auto_comment(lead_key):
    """Bot đăng comment cho 1 lead (đặc tả Bước 4). Mặc định chỉ cho lead nóng/rất nóng.

    Body tùy chọn: { "force": true } để bỏ qua giới hạn mức lead (vẫn giữ giới hạn quota/giờ).
    """
    body = request.get_json(silent=True) or {}
    force = bool(body.get('force', False))
    remote, _warning = _load_leads_from_supabase()
    source_lead = {}
    for item in _flatten_lead_groups(remote or _leads):
        if str(item.get('lead_key') or '') == str(lead_key):
            source_lead = item
            break
    if not source_lead:
        return jsonify({'ok': False, 'error': 'Không tìm thấy lead'}), 404

    ok, result = _auto_comment_lead(source_lead, post=None, force=force)
    if not ok:
        return jsonify({'ok': False, 'error': result}), 400
    updated = _normalise_lead({**source_lead, 'lead_key': lead_key, 'updated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z'}, source_lead.get('post_id') or '')
    _patch_lead_in_supabase(str(lead_key), updated)
    return jsonify({'ok': True, 'comment_id': result, 'lead': updated})


@app.route('/api/ai/comment-summaries', methods=['GET'])
def ai_comment_summaries_get():
    return jsonify(_comment_summaries)


@app.route('/api/ai/suggest-reply', methods=['POST'])
def ai_suggest_reply():
    global _reply_suggestions
    try:
        body = request.get_json() or {}
        post = body.get('post') or {}
        manual_comment = (body.get('comment') or '').strip()
        if not post:
            return jsonify({'ok': False, 'error': 'Không có bài viết'}), 400

        classifier = _get_classifier()
        if not classifier.api_key:
            return jsonify({'ok': False, 'error': 'Chưa cấu hình API key — thêm GEMINI_API_KEY vào .env hoặc key trong UI'}), 400

        suggestion = classifier.suggest_reply(post, manual_comment, _business_profile)
        if classifier.last_error and not suggestion:
            return jsonify({'ok': False, 'error': classifier.last_error}), 502
        if not suggestion:
            return jsonify({'ok': False, 'error': 'AI chưa tạo được gợi ý phù hợp'}), 502

        pid = suggestion.get('post_id') or post.get('id')
        suggestion['post_id'] = pid
        suggestion['group_id'] = post.get('_group_id', '')
        suggestion['post_url'] = post.get('permalink_url', '')
        _reply_suggestions[pid] = suggestion
        _save_reply_suggestions()

        supabase_ok, supabase_error = _save_reply_suggestion_to_supabase(suggestion)
        storage = 'supabase' if supabase_ok else 'local'
        payload = {'ok': True, 'suggestion': suggestion, 'storage': storage}
        if supabase_error:
            payload['warning'] = f'Đã lưu local, Supabase chưa ghi được: {supabase_error}'
        return jsonify(payload)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/ai/summarize-comments', methods=['POST'])
def ai_summarize_comments():
    global _comment_summaries
    try:
        body = request.get_json() or {}
        post = body.get('post') or {}
        force = bool(body.get('force', True))
        if not post or not post.get('id'):
            return jsonify({'ok': False, 'error': 'Không có bài viết'}), 400
        post_id = str(post.get('id'))
        group_id = str(post.get('_group_id') or DEFAULT_GROUP)
        if not force and post_id in _comment_summaries:
            return jsonify({'ok': True, 'summary': _comment_summaries[post_id], 'storage': 'local'})

        classifier = _get_classifier()
        if not classifier.api_key:
            return jsonify({'ok': False, 'error': 'Chưa cấu hình API key — thêm GEMINI_API_KEY vào .env hoặc key trong UI'}), 400

        loaded = get_api(group_id).get_post_comments(post_id, limit=500)
        if loaded is None:
            return jsonify({'ok': False, 'error': 'Không đọc được bình luận từ Facebook. Kiểm tra cookie/quyền nhóm.'}), 502
        comments = loaded.get('comments') or []
        total_count = int(loaded.get('total_count') or len(comments))

        post_for_ai = {**post, 'comments': {'data': comments, 'summary': {'total_count': total_count}}}
        summary = classifier.summarize_post_comments(post_for_ai, comments, total_count)
        if classifier.last_error and not summary:
            return jsonify({'ok': False, 'error': classifier.last_error}), 502
        if not summary:
            return jsonify({'ok': False, 'error': 'AI chưa tóm tắt được bình luận'}), 502

        staff = _current_staff()
        summary['created_by_staff_id'] = staff.get('id', '')
        summary['created_by_staff_name'] = staff.get('name', '')
        summary['created_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
        _comment_summaries[post_id] = summary
        _save_comment_summaries()

        supabase_ok, supabase_error = _save_comment_summary_to_supabase(summary)
        storage = 'supabase' if supabase_ok else 'local'
        payload = {'ok': True, 'summary': summary, 'storage': storage}
        if supabase_error:
            payload['warning'] = f'Đã lưu local, Supabase chưa ghi được: {supabase_error}'
        return jsonify(payload)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/ai/extract-leads', methods=['POST'])
def ai_extract_leads():
    global _leads
    body = request.get_json() or {}
    posts = body.get('posts', [])
    force = body.get('force', False)
    if not posts:
        return jsonify({'ok': False, 'error': 'Không có bài viết'})
    classifier = _get_classifier()
    if not classifier.api_key:
        return jsonify({'ok': False, 'error': 'Chưa cấu hình API key'})

    to_extract = [p for p in posts if force or p.get('id') not in _leads]
    if to_extract:
        results = classifier.extract_leads(to_extract)
        if classifier.last_error and not results:
            return jsonify({'ok': False, 'error': classifier.last_error}), 502
        for post in to_extract:
            pid = post.get('id')
            if pid:
                _leads[pid] = _postprocess_new_leads(
                    [_normalise_lead(item, pid) for item in results.get(pid, [])],
                    posts_by_id={str(p.get('id') or ''): p for p in to_extract},
                )
        _save_leads()
        flat_leads = [lead for items in _leads.values() for lead in (items or []) if str(lead.get('post_id') or '') in {str(p.get('id') or '') for p in to_extract}]
        supabase_ok, supabase_error = _save_leads_to_supabase(flat_leads)
    else:
        supabase_ok, supabase_error = True, ''

    all_results = {p['id']: _leads.get(p['id'], []) for p in posts if p.get('id')}
    payload = {'ok': True, 'leads': all_results}
    if classifier.last_error:
        payload['warning'] = classifier.last_error
    if not supabase_ok and supabase_error:
        payload['warning'] = f"{payload.get('warning', '')} Đã lưu local, Supabase chưa ghi lead được: {supabase_error}".strip()
    return jsonify(payload)


@app.route('/api/leads/from-comments', methods=['POST'])
def leads_from_comments():
    source = str((request.get_json(silent=True) or {}).get('source') or request.args.get('source') or '').strip().lower()
    post_id = str((request.get_json(silent=True) or {}).get('post_id') or request.args.get('post_id') or '').strip()
    rows, warning = _load_post_comment_rows(source=source, post_id=post_id, limit=5000)
    leads = _comment_rows_to_phone_leads(rows)
    leads = _postprocess_new_leads(leads)
    changed = _merge_leads_into_memory(leads)
    supabase_ok, supabase_error = _save_leads_to_supabase(leads)
    grouped = {}
    for lead in leads:
        grouped.setdefault(str(lead.get('post_id') or ''), []).append(lead)
    payload = {
        'ok': True,
        'count': len(leads),
        'new_count': changed,
        'leads': grouped,
        'storage': 'supabase' if supabase_ok else 'local',
    }
    final_warning = supabase_error or warning
    if final_warning:
        payload['warning'] = final_warning
    return jsonify(payload)


# ── Marketing Content Pipeline ─────────────────────────
@app.route('/api/content-pipeline', methods=['GET'])
def content_pipeline_get():
    articles = sorted(_content_pipeline.get('articles') or [], key=lambda item: str(item.get('published_at') or item.get('created_at') or ''), reverse=True)
    posts = sorted(_content_pipeline.get('posts') or [], key=lambda item: str(item.get('created_at') or ''), reverse=True)
    return jsonify({
        'ok': True,
        'sources': _content_pipeline.get('sources') or [],
        'articles': articles[:100],
        'posts': posts[:100],
        'stats': {
            'sources': len([s for s in (_content_pipeline.get('sources') or []) if s.get('active') is not False]),
            'articles': len(articles),
            'new_articles': len([a for a in articles if a.get('status') == 'new']),
            'draft_posts': len([p for p in posts if p.get('status') == 'draft']),
        },
    })


@app.route('/api/content-pipeline/research', methods=['POST'])
def content_pipeline_research():
    global _content_pipeline
    body = request.get_json(silent=True) or {}
    source_filter = str(body.get('source_filter') or body.get('sourceFilter') or 'all').strip().lower()
    sources = [s for s in (_content_pipeline.get('sources') or []) if s.get('active') is not False]
    if source_filter not in ('', 'all'):
        sources = [s for s in sources if str(s.get('id') or '').lower() == source_filter or str(s.get('type') or '').lower() == source_filter]

    existing = {str(item.get('id')): item for item in (_content_pipeline.get('articles') or [])}
    added = 0
    errors = []
    for source in sources:
        try:
            for article in _fetch_pipeline_rss(source, limit=12):
                if article['id'] not in existing:
                    existing[article['id']] = article
                    added += 1
        except Exception as e:
            errors.append(f"{source.get('name') or source.get('id')}: {e}")

    _content_pipeline['articles'] = sorted(existing.values(), key=lambda item: str(item.get('published_at') or item.get('created_at') or ''), reverse=True)[:250]
    _save_content_pipeline()
    payload = {'ok': True, 'added': added, 'article_count': len(_content_pipeline['articles'])}
    if errors:
        payload['warning'] = '; '.join(errors[:3])
    return jsonify(payload)


@app.route('/api/content-pipeline/write', methods=['POST'])
def content_pipeline_write():
    global _content_pipeline
    body = request.get_json(silent=True) or {}
    selections = body.get('selections') or []
    if not isinstance(selections, list) or not selections:
        return jsonify({'ok': False, 'error': 'Chọn ít nhất một tin để AI viết bài'}), 400

    articles_by_id = {str(item.get('id')): item for item in (_content_pipeline.get('articles') or [])}
    posts = list(_content_pipeline.get('posts') or [])
    created = []
    warnings = []
    staff = _current_staff()
    for item in selections[:10]:
        article_id = str((item or {}).get('id') or '').strip()
        fmt = str((item or {}).get('format') or 'pov').strip()
        article = articles_by_id.get(article_id)
        if not article:
            continue
        result = _pipeline_write_article(article, fmt)
        if result.get('ai_error'):
            warnings.append(result['ai_error'])
        post = {
            'id': _pipeline_post_id(article_id, fmt),
            'article_id': article_id,
            'article_title': article.get('title') or '',
            'article_url': article.get('url') or '',
            'source_name': article.get('source_name') or '',
            'format': fmt,
            'content': result.get('content') or '',
            'hashtags': result.get('hashtags') or '',
            'status': 'draft',
            'created_by_staff_id': staff.get('id', ''),
            'created_by_staff_name': staff.get('name', ''),
            'created_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        }
        posts.append(post)
        article['status'] = 'written'
        created.append(post)

    _content_pipeline['articles'] = list(articles_by_id.values())
    _content_pipeline['posts'] = sorted(posts, key=lambda row: str(row.get('created_at') or ''), reverse=True)[:250]
    _save_content_pipeline()
    payload = {'ok': True, 'count': len(created), 'posts': created}
    if warnings:
        payload['warning'] = '; '.join(dict.fromkeys(warnings))[:500]
    return jsonify(payload)


@app.route('/api/content-pipeline/posts/<post_id>', methods=['PATCH'])
def content_pipeline_post_update(post_id):
    body = request.get_json(silent=True) or {}
    changed = False
    for post in _content_pipeline.get('posts') or []:
        if str(post.get('id')) == str(post_id):
            for key in ('content', 'hashtags', 'status', 'scheduled_at', 'scheduled_targets', 'publish_results', 'published_at'):
                if key in body:
                    post[key] = body.get(key)
                    changed = True
            post['updated_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
            break
    if changed:
        _save_content_pipeline()
    return jsonify({'ok': changed})


@app.route('/api/content-pipeline/posts/<post_id>', methods=['DELETE'])
def content_pipeline_post_delete(post_id):
    before = len(_content_pipeline.get('posts') or [])
    _content_pipeline['posts'] = [post for post in (_content_pipeline.get('posts') or []) if str(post.get('id')) != str(post_id)]
    if len(_content_pipeline['posts']) != before:
        _save_content_pipeline()
    return jsonify({'ok': True, 'deleted': before - len(_content_pipeline['posts'])})


@app.route('/api/content-pipeline/posts/<post_id>/publish', methods=['POST'])
def content_pipeline_post_publish(post_id):
    body = request.get_json(silent=True) or {}
    targets = body.get('targets') or []
    if not isinstance(targets, list) or not targets:
        return jsonify({'ok': False, 'error': 'Chọn ít nhất một Page hoặc nhóm để đăng'}), 400
    for post in _content_pipeline.get('posts') or []:
        if str(post.get('id')) == str(post_id):
            result = _publish_content_pipeline_post(post, targets)
            post['publish_results'] = result.get('results') or []
            post['published_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
            post['status'] = 'posted' if result.get('ok') else 'failed'
            post['updated_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
            _save_content_pipeline()
            return jsonify(result)
    return jsonify({'ok': False, 'error': 'Không tìm thấy bản nháp'}), 404


@app.route('/api/content-pipeline/posts/<post_id>/schedule', methods=['POST'])
def content_pipeline_post_schedule(post_id):
    body = request.get_json(silent=True) or {}
    scheduled_at = str(body.get('scheduled_at') or '').strip()
    targets = body.get('targets') or []
    if not _parse_iso_datetime(scheduled_at):
        return jsonify({'ok': False, 'error': 'Thời gian lên lịch không hợp lệ'}), 400
    if not isinstance(targets, list) or not targets:
        return jsonify({'ok': False, 'error': 'Chọn ít nhất một Page hoặc nhóm để lên lịch'}), 400
    for post in _content_pipeline.get('posts') or []:
        if str(post.get('id')) == str(post_id):
            post['status'] = 'scheduled'
            post['scheduled_at'] = scheduled_at
            post['scheduled_targets'] = targets
            post['updated_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
            _save_content_pipeline()
            return jsonify({'ok': True, 'post': post})
    return jsonify({'ok': False, 'error': 'Không tìm thấy bản nháp'}), 404


@app.route('/api/content-pipeline/scheduled/run', methods=['GET', 'POST'])
def content_pipeline_run_scheduled():
    now = datetime.now(timezone.utc)
    ran = 0
    results = []
    for post in _content_pipeline.get('posts') or []:
        if str(post.get('status') or '') != 'scheduled':
            continue
        due_at = _parse_iso_datetime(post.get('scheduled_at'))
        if not due_at or due_at > now:
            continue
        targets = post.get('scheduled_targets') or []
        result = _publish_content_pipeline_post(post, targets if isinstance(targets, list) else [])
        post['publish_results'] = result.get('results') or []
        post['published_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
        post['status'] = 'posted' if result.get('ok') else 'failed'
        post['updated_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
        results.append({'id': post.get('id'), **result})
        ran += 1
    if ran:
        _save_content_pipeline()
    return jsonify({'ok': True, 'ran': ran, 'results': results})


# ── Supabase ───────────────────────────────────────────
@app.route('/api/supabase/health')
def supabase_health():
    return jsonify({'enabled': USE_SUPABASE, **sb.ping()})


@app.route('/api/saved-posts')
def saved_posts():
    if not USE_SUPABASE:
        return jsonify({'ok': False, 'error': 'Supabase chưa được cấu hình'}), 400
    limit = request.args.get('limit', 100, type=int)
    group_id = (request.args.get('group_id') or '').strip() or None
    try:
        rows = sb.list_saved_posts(limit=limit, group_id=group_id)
        return jsonify({'ok': True, 'count': len(rows), 'posts': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Start ──────────────────────────────────────────────
_load_state()
threading.Thread(target=_poll_telegram, daemon=True).start()
threading.Thread(target=_sla_monitor_loop, daemon=True).start()
threading.Thread(target=_auto_scan_loop, daemon=True).start()

if __name__ == '__main__':
    print(f'[server] supabase={"on" if USE_SUPABASE else "off"} | http://localhost:{PORT}')
    app.run(debug=False, port=PORT)
