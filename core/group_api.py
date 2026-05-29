import requests
import os
from typing import Optional, List, Dict
from core.token_gen import FacebookTokenGenerator

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(BASE_DIR, 'data', 'token_success.txt')
COOKIE_FILE = os.path.join(BASE_DIR, 'data', 'cookie.txt')
FB_CLIENT_ID = '350685531728'
GRAPH_URL = 'https://graph.facebook.com/v21.0'


def _post_object_id(post_id: str) -> str:
    """Facebook feed IDs are often group_id_post_id, while comment edges need post_id."""
    post_id = str(post_id or '').strip()
    if '_' in post_id:
        return post_id.rsplit('_', 1)[-1]
    return post_id


def load_token(token_file: str = None) -> Optional[str]:
    token_file = token_file or TOKEN_FILE
    if not os.path.exists(token_file):
        return None
    with open(token_file, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return None
    return lines[-1].split('|')[-1]


def load_cookie(cookie: str = None) -> Optional[str]:
    if cookie:
        return cookie.strip() or None
    if not os.path.exists(COOKIE_FILE):
        return None
    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        return f.read().strip() or None


def refresh_token(cookie: str = None, token_file: str = None) -> Optional[str]:
    cookie = load_cookie(cookie)
    if not cookie:
        print('Không tìm thấy cookie.txt — cần cập nhật cookie thủ công')
        return None
    print('🔄 Token hết hạn, đang lấy token mới từ cookie...')
    return FacebookTokenGenerator(FB_CLIENT_ID, cookie, token_file).GetToken()


class FacebookGroupAPI:
    def __init__(self, group_id: str, cookie: str = None, token_file: str = None):
        self.group_id = group_id
        self.cookie = load_cookie(cookie)
        self.token_file = token_file
        self.access_token = load_token(token_file) or refresh_token(self.cookie, token_file)

    def _is_expired(self, data: dict) -> bool:
        return data.get('error', {}).get('code') == 190

    def _call(self, method: str, url: str, **kwargs) -> Optional[dict]:
        for attempt in range(2):
            kwargs.setdefault('params', {})['access_token'] = self.access_token
            resp = getattr(requests, method)(url, **kwargs)
            data = resp.json()
            if self._is_expired(data):
                if attempt == 0:
                    new_token = refresh_token(self.cookie, self.token_file)
                    if new_token:
                        self.access_token = new_token
                        continue
                print('Không thể refresh token — kiểm tra lại cookie')
                return None
            return data
        return None

    def get_posts(self, limit: int = 10) -> Optional[List[Dict]]:
        data = self._call('get', f'{GRAPH_URL}/{self.group_id}/feed', params={
            'fields': 'id,message,from,created_time,updated_time,is_hidden,permalink_url,attachments,comments.limit(50).summary(true){id,message,from,created_time},reactions.limit(0).summary(true),shares',
            'limit': limit,
        })
        posts = data.get('data') if data else None
        if not posts:
            return posts
        for post in posts:
            self._fill_post_engagement(post)
        return posts

    def _fill_post_engagement(self, post: Dict) -> None:
        comments = post.get('comments') or {}
        has_comment_count = isinstance(comments.get('summary'), dict) and comments.get('summary', {}).get('total_count') is not None
        if has_comment_count or not post.get('id'):
            return

        object_id = _post_object_id(post.get('id', ''))
        if not object_id or object_id == post.get('id'):
            return
        data = self._call('get', f'{GRAPH_URL}/{object_id}', params={
            'fields': 'comments.limit(50).summary(true){id,message,from,created_time,attachment},reactions.limit(0).summary(true),shares',
        })
        if not data or data.get('error'):
            return

        fb_comments = data.get('comments')
        if isinstance(fb_comments, dict):
            if not isinstance(fb_comments.get('summary'), dict):
                fb_comments['summary'] = {}
            if fb_comments['summary'].get('total_count') is None:
                fb_comments['summary']['total_count'] = len(fb_comments.get('data') or [])
            post['comments'] = fb_comments
        if data.get('reactions'):
            post['reactions'] = data['reactions']
        if data.get('shares'):
            post['shares'] = data['shares']

    def create_post(self, message: str, page_token: str = None) -> Optional[dict]:
        token = page_token or self.access_token
        resp = requests.post(
            f'{GRAPH_URL}/{self.group_id}/feed',
            params={'access_token': token, 'message': message}
        )
        return resp.json()

    def create_page_post(self, page_id: str, message: str, page_token: str) -> Optional[dict]:
        resp = requests.post(
            f'{GRAPH_URL}/{page_id}/feed',
            params={'access_token': page_token, 'message': message}
        )
        return resp.json()

    def get_pages(self) -> Optional[list]:
        data = self._call('get', f'{GRAPH_URL}/me/accounts', params={'fields': 'id,name,access_token'})
        return data.get('data') if data else None

    def post_comment(self, post_id: str, message: str, page_token: str = None, attachment_url: str = '') -> Optional[dict]:
        token = page_token or self.access_token
        params = {'access_token': token}
        if message:
            params['message'] = message
        if attachment_url:
            params['attachment_url'] = attachment_url
        resp = requests.post(
            f'{GRAPH_URL}/{post_id}/comments',
            params=params
        )
        return resp.json()

    def get_post_comments(self, post_id: str, limit: int = 500) -> Optional[dict]:
        comments: List[Dict] = []
        fields = 'id,message,from,created_time,attachment,comments.limit(50).summary(true){id,message,from,created_time,attachment}'
        page_limit = min(max(limit, 1), 100)
        params = {
            'fields': fields,
            'limit': page_limit,
            'summary': 'true',
            'filter': 'stream',
        }
        data = self._call('get', f'{GRAPH_URL}/{post_id}/comments', params=dict(params))
        if data and data.get('error') and '_' in str(post_id):
            data = self._call('get', f'{GRAPH_URL}/{_post_object_id(post_id)}/comments', params=dict(params))
        if data is None:
            return None
        if data.get('error'):
            return None

        total_count = ((data.get('summary') or {}).get('total_count') or 0)
        while data and len(comments) < limit:
            for item in data.get('data') or []:
                comments.append(item)
                if len(comments) >= limit:
                    break
            next_url = ((data.get('paging') or {}).get('next') or '')
            if not next_url or len(comments) >= limit:
                break
            try:
                resp = requests.get(next_url, timeout=30)
                data = resp.json()
                if self._is_expired(data):
                    import re
                    new_token = refresh_token(self.cookie, self.token_file)
                    if not new_token:
                        break
                    self.access_token = new_token
                    next_url = re.sub(r'access_token=[^&]+', f'access_token={self.access_token}', next_url)
                    resp = requests.get(next_url, timeout=30)
                    data = resp.json()
                if 'error' in data:
                    break
            except Exception:
                break
        return {'comments': comments[:limit], 'total_count': total_count or len(comments)}

    def resolve_slug(self, slug: str) -> Optional[dict]:
        data = self._call('get', f'{GRAPH_URL}/{slug}', params={'fields': 'id,name'})
        if data and 'id' in data:
            return data
        return _scrape_group_id(slug, self.cookie)

    def check_membership(self, group_id: str) -> bool:
        """Check if current user is a member of the group."""
        # Try to get /member endpoint which requires membership
        data = self._call('get', f'{GRAPH_URL}/{group_id}', params={'fields': 'id,name'})
        if data is None or 'error' in data:
            return False
        # Also try feed access — if feed returns error, not a member
        feed = self._call('get', f'{GRAPH_URL}/{group_id}/feed', params={'fields': 'id', 'limit': 1})
        if feed is None or 'error' in feed:
            return False
        # For public groups, feed is accessible even without membership
        # Use cookie-based check as fallback
        return self._cookie_check_membership(group_id)

    def _cookie_check_membership(self, group_id: str) -> bool:
        """Check membership via mbasic.facebook.com (cookie-based)."""
        import re
        cookie = load_cookie(self.cookie)
        if not cookie:
            return True  # Can't check, assume member
        try:
            resp = requests.get(
                f'https://mbasic.facebook.com/groups/{group_id}',
                headers={
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
                    'Accept': 'text/html',
                    'Cookie': cookie,
                },
                timeout=15,
                allow_redirects=True,
            )
            html = resp.text
            # If redirected to login
            if '/login' in resp.url or 'Đăng nhập' in html[:500]:
                return True  # Can't determine, assume member
            # Check for leave/member indicators
            if re.search(r'leave_group|rời nhóm|Rời Nhóm|Đã tham gia', html, re.I):
                return True
            # Check for join button — means NOT a member
            if re.search(r'join.*group|tham gia nhóm|Tham Gia Nhóm|/join/', html, re.I):
                return False
            return True  # Default assume member
        except Exception:
            return True

    def join_group(self, group_id: str) -> dict:
        import re
        cookie = load_cookie(self.cookie)
        if not cookie:
            return {'ok': False, 'error': 'Không có cookie'}
        try:
            sess = requests.Session()
            r = sess.get(
                f'https://mbasic.facebook.com/groups/{group_id}',
                headers={
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
                    'Accept': 'text/html',
                    'Cookie': cookie,
                },
                timeout=15,
            )
            html = r.text
            if re.search(r'leave_group|rời nhóm|Rời Nhóm', html, re.I):
                return {'ok': True, 'already_member': True, 'msg': 'Đã là thành viên'}
            m = re.search(r'action="(/groups/[^"]*join[^"]*)"', html, re.I) or \
                re.search(r'action="(/a/group/join[^"]*)"', html, re.I)
            if not m:
                return {'ok': False, 'error': 'Nhóm riêng tư hoặc không tìm được nút tham gia'}
            form_url = 'https://mbasic.facebook.com' + m.group(1).replace('&amp;', '&')
            inputs = {k: v for k, v in re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', html)}
            r2 = sess.post(
                form_url, data=inputs,
                headers={
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
                    'Cookie': cookie,
                    'Referer': f'https://mbasic.facebook.com/groups/{group_id}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=15,
            )
            if r2.status_code < 400:
                return {'ok': True, 'msg': 'Đã gửi yêu cầu tham gia nhóm'}
            return {'ok': False, 'error': f'Lỗi HTTP {r2.status_code}'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}


def _scrape_group_id(slug: str, cookie: str = None) -> Optional[dict]:
    cookie = load_cookie(cookie)
    if not cookie:
        return None
    import re as _re
    from collections import Counter
    try:
        resp = requests.get(
            f'https://mbasic.facebook.com/groups/{slug}?v=info',
            headers={
                'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
                'accept': 'text/html',
                'accept-language': 'vi-VN,vi;q=0.9,en;q=0.5',
                'Cookie': cookie,
            },
            timeout=15,
            allow_redirects=True,
        )
        html = resp.text
        # Detect login redirect
        if '/login' in resp.url or 'Đăng nhập' in html[:500] or '<title>Log in' in html[:500]:
            return None
        # Detect error pages
        title_m = _re.search(r'<title>([^<]+)</title>', html)
        if title_m:
            title = title_m.group(1).strip()
            # Skip if title is a login/error page
            if any(k in title.lower() for k in ['đăng nhập', 'log in', 'login', 'error', 'not found']):
                return None
        # Lấy số xuất hiện nhiều nhất trong khoảng 10-16 chữ số (độ dài ID group FB)
        candidates = _re.findall(r'\b(\d{10,16})\b', html)
        if not candidates:
            return None
        freq = Counter(candidates)
        gid = freq.most_common(1)[0][0]
        # Lấy tên group từ title
        name = title_m.group(1).replace('| Facebook', '').strip() if title_m else slug
        return {'id': gid, 'name': name}
    except Exception:
        pass
    return None
