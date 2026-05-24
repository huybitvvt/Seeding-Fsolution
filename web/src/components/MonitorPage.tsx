'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AuthPanel } from '@/components/AuthPanel';
import { PostCard } from '@/components/PostCard';
import { SaleSetupPanel } from '@/components/SaleSetupPanel';
import { api } from '@/lib/api';
import type { CommentSummary, FbPage, FbPost, GroupRow, Lead, ReplySuggestion, StaffAccount, StoredPostComment } from '@/lib/types';
import { extractSlug } from '@/lib/utils';

type AiProviders = Record<string, { default_model?: string }>;
type AiConfig = {
  provider?: string;
  model?: string;
  keys_masked?: Record<string, string>;
  auto_classify?: boolean;
};

type JoinPrompt = { id: string; name: string };

export function MonitorPage() {
  const [groups, setGroups] = useState<string[]>([]);
  const [groupNames, setGroupNames] = useState<Record<string, string>>({});
  const [keywords, setKeywords] = useState<string[]>([]);
  const [kwInp, setKwInp] = useState('');
  const [tgIds, setTgIds] = useState<string[]>([]);
  const [tgInp, setTgInp] = useState('');
  const [tgStatus, setTgStatus] = useState('');
  const [pages, setPages] = useState<FbPage[]>([]);
  const [allPosts, setAllPosts] = useState<FbPost[]>([]);
  const [classifications, setClassifications] = useState<Record<string, string>>({});
  const [leads, setLeads] = useState<Record<string, Lead[]>>({});
  const [replySuggestions, setReplySuggestions] = useState<Record<string, ReplySuggestion>>({});
  const [commentSummaries, setCommentSummaries] = useState<Record<string, CommentSummary>>({});
  const [leadsBusy, setLeadsBusy] = useState(false);
  const [aiProviders, setAiProviders] = useState<AiProviders>({});
  const [aiConfig, setAiConfig] = useState<AiConfig>({});
  const [aiProvider, setAiProvider] = useState('gemini');
  const [aiAutoClassify, setAiAutoClassify] = useState(false);
  const [aiKeyInput, setAiKeyInput] = useState('');
  const [aiKeyEdit, setAiKeyEdit] = useState(false);
  const [aiStatus, setAiStatus] = useState('');
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [setupRequired, setSetupRequired] = useState(false);
  const [authStatus, setAuthStatus] = useState('');
  const [currentStaff, setCurrentStaff] = useState<StaffAccount | null>(null);
  const [staffRows, setStaffRows] = useState<StaffAccount[]>([]);
  const [canManageStaff, setCanManageStaff] = useState(false);
  const [staffStatus, setStaffStatus] = useState('');
  const [todayCommentCount, setTodayCommentCount] = useState<number | null>(null);

  const [limit, setLimit] = useState(10);
  const [intervalMin, setIntervalMin] = useState(5);
  const [autoOn, setAutoOn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [feedError, setFeedError] = useState('');
  const [toolStatus, setToolStatus] = useState('');
  const statusBaseRef = useRef('');
  const [headerSub, setHeaderSub] = useState('Đang tải...');

  const [catFilter, setCatFilter] = useState('');
  const [groupInp, setGroupInp] = useState('');
  const [groupBusy, setGroupBusy] = useState(false);
  const [joinPrompt, setJoinPrompt] = useState<JoinPrompt | null>(null);
  const [joinMsg, setJoinMsg] = useState('');
  const [joinBusy, setJoinBusy] = useState(false);

  const [postModal, setPostModal] = useState(false);
  const [postSelected, setPostSelected] = useState<Record<string, boolean>>({});
  const [postPageId, setPostPageId] = useState('');
  const [postContent, setPostContent] = useState('');
  const [postResult, setPostResult] = useState('');
  const [postSubmitting, setPostSubmitting] = useState(false);

  const [fbCommentModalPost, setFbCommentModalPost] = useState<FbPost | null>(null);
  const [fbCommentKeywords, setFbCommentKeywords] = useState('quan tâm, đặt hàng, sđt, địa chỉ, ib, giá');
  const [fbCommentRows, setFbCommentRows] = useState<StoredPostComment[]>([]);
  const [fbCommentStatus, setFbCommentStatus] = useState('');
  const [fbCommentBusy, setFbCommentBusy] = useState(false);

  const [tiktokModal, setTiktokModal] = useState(false);
  const [tiktokUrl, setTiktokUrl] = useState('');
  const [tiktokKeywords, setTiktokKeywords] = useState('quan tâm, đặt hàng, sđt, địa chỉ, ib, giá');
  const [tiktokRows, setTiktokRows] = useState<StoredPostComment[]>([]);
  const [tiktokStatus, setTiktokStatus] = useState('');
  const [tiktokBusy, setTiktokBusy] = useState(false);

  const [lightbox, setLightbox] = useState<string | null>(null);
  const [classifyBusy, setClassifyBusy] = useState(false);

  const autoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const groupsRef = useRef<string[]>([]);
  const limitRef = useRef(10);
  const autoOnRef = useRef(false);

  useEffect(() => {
    groupsRef.current = groups;
  }, [groups]);
  useEffect(() => {
    limitRef.current = limit;
  }, [limit]);
  useEffect(() => {
    autoOnRef.current = autoOn;
  }, [autoOn]);

  const checkAuth = useCallback(async () => {
    try {
      const r = await api('/api/auth/status');
      const d = await r.json();
      setSetupRequired(!!d.setup_required && !d.simple_login);
      setAuthenticated(!!d.authenticated);
      setCurrentStaff(d.staff || null);
      setAuthStatus('');
    } catch {
      setSetupRequired(false);
      setAuthenticated(false);
      setCurrentStaff(null);
      setAuthStatus('Không kết nối được server');
    } finally {
      setAuthChecked(true);
    }
  }, []);

  const loadStaffCookies = useCallback(async () => {
    try {
      const r = await api('/api/staff-cookies');
      const d = await r.json();
      setStaffRows(d.staff || []);
      setCanManageStaff(!!d.can_manage);
      if (d.warning) setStaffStatus(`⚠️ ${d.warning}`);
    } catch {
      setStaffStatus('Không tải được cookie nhân sự');
    }
  }, []);

  const loadTodayCommentStats = useCallback(async () => {
    try {
      const r = await api('/api/comment-stats/today');
      const d = await r.json();
      if (d.ok) setTodayCommentCount(d.success_count ?? 0);
    } catch {
      setTodayCommentCount(null);
    }
  }, []);

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  const loadPages = useCallback(async () => {
    try {
      const r = await api('/api/pages');
      const d = await r.json();
      if (Array.isArray(d)) setPages(d);
    } catch {
      /* ignore */
    }
  }, []);

  const loadGroupName = useCallback(async (gid: string) => {
    try {
      const r = await api('/api/groups/resolve?slug=' + encodeURIComponent(gid));
      const d = await r.json();
      if (d.ok && d.name) {
        setGroupNames((prev) => ({ ...prev, [gid]: d.name }));
      }
    } catch {
      /* ignore */
    }
  }, []);

  const loadTg = useCallback(async () => {
    try {
      const r = await api('/api/telegram/chatids');
      setTgIds(await r.json());
    } catch {
      /* ignore */
    }
  }, []);

  const loadPosts = useCallback(async (): Promise<FbPost[] | null> => {
    const gids = groupsRef.current;
    const lim = limitRef.current;
    if (!gids.length) return null;
    setLoading(true);
    setFeedError('');
    setToolStatus('Đang tải...');
    try {
      const res = await api(`/api/posts?limit=${lim}&groups=${gids.join(',')}`);
      const data = await res.json();
      if (!res.ok || data.error) {
        const msg =
          data.error ||
          (res.status === 401
            ? 'Cookie/token Facebook hết hạn — cập nhật data/cookie.txt rồi restart backend'
            : `Lỗi tải bài (${res.status})`);
        setAllPosts([]);
        setFeedError(msg);
        setToolStatus('Lỗi xác thực');
        statusBaseRef.current = '';
        return null;
      }
      setAllPosts(data);
      const now = new Date().toLocaleTimeString('vi-VN');
      let known: string[] = [];
      try {
        known = JSON.parse(typeof window !== 'undefined' ? localStorage.getItem('seenIds') || '[]' : '[]');
      } catch {
        known = [];
      }
      const knownSet = new Set(known);
      const fresh = data.filter((p: FbPost) => !knownSet.has(p.id));
      data.forEach((p: FbPost) => knownSet.add(p.id));
      const nextKnown = [...knownSet].slice(-500);
      if (typeof window !== 'undefined') localStorage.setItem('seenIds', JSON.stringify(nextKnown));
      const base = `${data.length} bài · ${now}`;
      statusBaseRef.current = base;
      const nb = fresh.length && knownSet.size > fresh.length ? ` +${fresh.length} mới` : '';
      setToolStatus(base + nb);
      return data as FbPost[];
    } catch {
      setAllPosts([]);
      setToolStatus('Lỗi');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (groups.length === 1) {
      const n = groupNames[groups[0]!] || groups[0];
      setHeaderSub(n || '...');
    } else {
      setHeaderSub(groups.length ? `${groups.length} nhóm đang theo dõi` : '...');
    }
  }, [groups, groupNames]);

  const matchKw = useCallback(
    (post: FbPost) => {
      if (!keywords.length) return true;
      const hay = `${post.message || ''} ${post.from?.name || ''}`.toLowerCase();
      return keywords.some((k) => hay.includes(k.toLowerCase()));
    },
    [keywords],
  );

  const filteredPosts = allPosts.filter((p) => {
    if (!matchKw(p)) return false;
    if (catFilter && classifications[p.id] !== catFilter) return false;
    return true;
  });

  const catOptions = [...new Set(Object.values(classifications))].sort();

  useEffect(() => {
    if (!authChecked || !authenticated) return;
    let cancelled = false;
    (async () => {
      try {
        const sr = await api('/api/settings');
        const s = await sr.json();
        if (!cancelled) {
          setIntervalMin(s.interval || 5);
          setAutoOn(s.auto_refresh ?? true);
        }
      } catch {
        if (!cancelled) setAutoOn(true);
      }

      let autoClassify = false;
      try {
        const [pRes, cRes, clRes, lRes, rsRes, csRes] = await Promise.all([
          api('/api/ai/providers'),
          api('/api/ai/config'),
          api('/api/ai/classifications'),
          api('/api/ai/leads'),
          api('/api/ai/reply-suggestions'),
          api('/api/ai/comment-summaries'),
        ]);
        if (cancelled) return;
        setAiProviders(await pRes.json());
        const cfg = await cRes.json();
        setAiConfig(cfg);
        setAiProvider(cfg.provider || 'gemini');
        autoClassify = !!cfg.auto_classify;
        setAiAutoClassify(autoClassify);
        setClassifications(await clRes.json());
        setLeads(await lRes.json());
        setReplySuggestions(await rsRes.json());
        setCommentSummaries(await csRes.json());
      } catch {
        /* ignore */
      }

      let rows: GroupRow[] = [];
      try {
        const r = await api('/api/groups');
        rows = await r.json();
      } catch {
        /* ignore */
      }
      if (cancelled) return;
      const gIds = rows.map((x) => x.id);
      const gn: Record<string, string> = {};
      rows.forEach((row) => {
        if (row.name) gn[row.id] = row.name;
      });
      groupsRef.current = gIds;
      setGroups(gIds);
      setGroupNames((prev) => ({ ...prev, ...gn }));

      await Promise.allSettled(gIds.map((g) => loadGroupName(g)));
      await Promise.allSettled(
        gIds.map((g) =>
          api('/api/groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: g, name: gn[g] || '' }),
          }),
        ),
      );
      await loadTg();
      await loadPages();
      await loadStaffCookies();
      await loadTodayCommentStats();

      const posts = await loadPosts();
      if (cancelled) return;
      if (autoClassify && posts?.length) {
        try {
          const r = await api('/api/ai/classify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ posts }),
          });
          const d = await r.json();
          if (d.ok && !cancelled) {
            setClassifications((c) => ({ ...c, ...d.classifications }));
          }
        } catch {
          /* ignore */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authChecked, authenticated, loadGroupName, loadPages, loadPosts, loadStaffCookies, loadTg, loadTodayCommentStats]);

  useEffect(() => {
    if (autoTimerRef.current) {
      clearTimeout(autoTimerRef.current);
      autoTimerRef.current = null;
    }
    if (!autoOn) {
      setToolStatus((t) => statusBaseRef.current || t);
      return;
    }
    const ms = Math.max(1, intervalMin) * 60 * 1000;
    const schedule = () => {
      autoTimerRef.current = setTimeout(() => {
        void loadPosts().finally(() => {
          if (autoOnRef.current) schedule();
        });
      }, ms);
    };
    schedule();
    return () => {
      if (autoTimerRef.current) clearTimeout(autoTimerRef.current);
    };
  }, [autoOn, intervalMin, loadPosts]);

  function saveSettings(auto: boolean, interval: number) {
    void api('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_refresh: auto, interval }),
    });
  }

  function toggleAuto() {
    const next = !autoOn;
    setAutoOn(next);
    saveSettings(next, intervalMin);
    if (!next) setToolStatus(statusBaseRef.current || '');
  }

  function addKw() {
    const v = kwInp.trim();
    if (!v || keywords.includes(v)) {
      setKwInp('');
      return;
    }
    setKeywords((k) => [...k, v]);
    setKwInp('');
  }

  function removeKw(kw: string) {
    setKeywords((k) => k.filter((x) => x !== kw));
  }

  async function addGroup() {
    const raw = groupInp.trim();
    if (!raw) return;
    setGroupInp('');
    setGroupBusy(true);
    const slug = extractSlug(raw);
    const prev = statusBaseRef.current || toolStatus;
    setToolStatus(`🔍 Đang tìm "${slug}"...`);
    try {
      const r = await api('/api/groups/resolve?slug=' + encodeURIComponent(slug));
      const d = await r.json();
      if (d.ok) {
        if (d.name) setGroupNames((g) => ({ ...g, [d.id]: d.name }));
        if (!d.is_member) {
          setToolStatus(prev);
          setJoinPrompt({ id: d.id, name: d.name || d.id });
        } else {
          await api('/api/groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: d.id, name: d.name || '' }),
          });
          setGroups((g) => (g.includes(d.id) ? g : [...g, d.id]));
          setToolStatus(`✅ Đã thêm: ${d.name || d.id}`);
          setTimeout(() => setToolStatus(prev), 5000);
        }
      } else {
        if (/^\d{10,}$/.test(slug)) {
          setToolStatus(prev);
          setJoinPrompt({ id: slug, name: slug });
        } else {
          setToolStatus(`❌ Không tìm được: ${d.error}`);
          setTimeout(() => setToolStatus(prev), 4000);
        }
      }
    } catch {
      setToolStatus('❌ Lỗi kết nối');
      setTimeout(() => setToolStatus(prev), 4000);
    }
    setGroupBusy(false);
  }

  async function forceAddGroup(gid: string, gname: string) {
    await api('/api/groups', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: gid, name: gname }),
    });
    setGroups((g) => (g.includes(gid) ? g : [...g, gid]));
    setGroupNames((prev) => ({ ...prev, [gid]: gname }));
    setJoinPrompt(null);
    setJoinMsg('');
  }

  async function joinGroupAct(gid: string, gname: string) {
    setJoinBusy(true);
    setJoinMsg('');
    try {
      const r = await api(`/api/groups/${gid}/join`, { method: 'POST' });
      const d = await r.json();
      if (d.ok) {
        if (d.already_member) {
          await api('/api/groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: gid, name: gname }),
          });
          setGroups((g) => (g.includes(gid) ? g : [...g, gid]));
          setJoinPrompt(null);
        } else {
          setJoinMsg('✅ ' + d.msg + ' — Chờ admin duyệt rồi thêm lại nhóm.');
        }
      } else {
        setJoinMsg('❌ ' + (d.error || 'Lỗi không xác định'));
      }
    } catch {
      setJoinMsg('❌ Lỗi kết nối');
    }
    setJoinBusy(false);
  }

  async function removeGroup(gid: string) {
    if (groups.length <= 1) return;
    await api(`/api/groups/${gid}`, { method: 'DELETE' });
    setGroups((g) => g.filter((x) => x !== gid));
  }

  async function addTg() {
    const cid = tgInp.trim().replace(/[^0-9-]/g, '');
    if (!cid) return;
    setTgInp('');
    const r = await api('/api/telegram/chatids', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: cid }),
    });
    const d = await r.json();
    if (d.ok) setTgIds(d.chat_ids);
  }

  async function removeTg(cid: string) {
    const r = await api(`/api/telegram/chatids/${cid}`, { method: 'DELETE' });
    const d = await r.json();
    setTgIds(d.chat_ids);
  }

  async function testTg(cid: string) {
    setTgStatus('⏳ Đang gửi...');
    try {
      const r = await api(`/api/telegram/test/${cid}`, { method: 'POST' });
      const d = await r.json();
      setTgStatus(d.ok ? '✅ Gửi thành công!' : '❌ ' + (d.error || 'Lỗi'));
    } catch {
      setTgStatus('❌ Lỗi kết nối');
    }
    setTimeout(() => setTgStatus(''), 3000);
  }

  function openPostModal() {
    const sel: Record<string, boolean> = {};
    groups.forEach((g) => {
      sel[g] = true;
    });
    setPostSelected(sel);
    setPostPageId('');
    setPostContent('');
    setPostResult('');
    setPostModal(true);
  }

  async function submitPost() {
    const selectedGroups = groups.filter((g) => postSelected[g]);
    const message = postContent.trim();
    if (!message) return;
    if (!selectedGroups.length) {
      setPostResult('❌ Chọn ít nhất 1 nhóm');
      return;
    }
    setPostSubmitting(true);
    setPostResult(`⏳ Đang đăng vào ${selectedGroups.length} nhóm...`);
    let ok = 0;
    let fail = 0;
    for (const group_id of selectedGroups) {
      try {
        const r = await api('/api/post', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group_id, page_id: postPageId, message }),
        });
        const d = await r.json();
        if (d.ok) ok++;
        else fail++;
      } catch {
        fail++;
      }
      setPostResult(`⏳ Đã đăng ${ok + fail}/${selectedGroups.length} (✅${ok} ❌${fail})`);
    }
    if (fail === 0) {
      setPostResult(`✅ Đăng thành công ${ok}/${selectedGroups.length} nhóm!`);
      setPostContent('');
      setTimeout(() => setPostModal(false), 2000);
    } else {
      setPostResult(`✅ ${ok} thành công, ❌ ${fail} thất bại`);
    }
    setPostSubmitting(false);
  }

  function parseKeywordInput(value: string): string[] {
    return value
      .split(/[\n,;]+/)
      .map((x) => x.trim())
      .filter(Boolean)
      .slice(0, 50);
  }

  function openFbCommentExplorer(post: FbPost) {
    setFbCommentModalPost(post);
    setFbCommentRows([]);
    setFbCommentStatus('');
  }

  async function fetchFacebookCommentsForFilter() {
    if (!fbCommentModalPost) return;
    setFbCommentBusy(true);
    setFbCommentStatus('Đang lấy toàn bộ comment Facebook...');
    try {
      const r = await api('/api/post-comments/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          post: fbCommentModalPost,
          keywords: parseKeywordInput(fbCommentKeywords),
          limit: 1000,
        }),
      });
      const d = await r.json();
      if (d.ok) {
        setFbCommentRows(d.comments || []);
        const warn = d.warning ? ` · ${d.warning}` : '';
        setFbCommentStatus(`Đã đọc ${d.fetched_comment_count}/${d.comment_count} comment · khớp ${d.matched_count} · lưu ${d.storage}${warn}`);
      } else {
        setFbCommentRows([]);
        setFbCommentStatus(`Lỗi: ${d.error || 'Không lấy được comment'}`);
      }
    } catch {
      setFbCommentRows([]);
      setFbCommentStatus('Lỗi kết nối backend');
    }
    setFbCommentBusy(false);
  }

  async function fetchTiktokCommentsForFilter() {
    const url = tiktokUrl.trim();
    if (!url) {
      setTiktokStatus('Dán link video TikTok trước');
      return;
    }
    setTiktokBusy(true);
    setTiktokStatus('Đang lấy comment TikTok...');
    try {
      const r = await api('/api/tiktok/comments/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          keywords: parseKeywordInput(tiktokKeywords),
          limit: 500,
        }),
      });
      const d = await r.json();
      if (d.ok) {
        setTiktokRows(d.comments || []);
        const warn = d.warning ? ` · ${d.warning}` : '';
        setTiktokStatus(`Đã đọc ${d.fetched_comment_count} comment · khớp ${d.matched_count} · lưu ${d.storage}${warn}`);
      } else {
        setTiktokRows([]);
        setTiktokStatus(`Lỗi: ${d.error || 'Không lấy được comment TikTok'}`);
      }
    } catch {
      setTiktokRows([]);
      setTiktokStatus('Lỗi kết nối backend');
    }
    setTiktokBusy(false);
  }

  async function onProviderChange(next: string) {
    setAiProvider(next);
    setAiStatus('');
    try {
      await api('/api/ai/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: next,
          model: (aiProviders[next] || {}).default_model || '',
        }),
      });
    } catch {
      setAiStatus('❌ Không kết nối được backend khi đổi AI');
    }
  }

  async function saveAiKey() {
    if (!aiKeyInput.trim()) {
      setAiStatus('❌ Nhập API key');
      return;
    }
    setAiStatus('⏳ Đang lưu...');
    const model = (aiProviders[aiProvider] || {}).default_model || '';
    try {
      const r = await api('/api/ai/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: aiProvider, model, key: aiKeyInput.trim() }),
      });
      const d = await r.json();
      if (d.ok) {
        setAiStatus('✅ Đã lưu key!');
        const cRes = await api('/api/ai/config');
        setAiConfig(await cRes.json());
        setAiKeyEdit(false);
        setAiKeyInput('');
      } else setAiStatus('❌ ' + (d.error || 'Lỗi lưu key'));
    } catch {
      setAiStatus('❌ Không kết nối được backend. Kiểm tra Flask port 5000 và refresh lại trang.');
    }
    setTimeout(() => setAiStatus(''), 3000);
  }

  async function deleteAiKey() {
    if (!confirm(`Xoá API key của ${aiProvider.toUpperCase()}?`)) return;
    try {
      const r = await api(`/api/ai/key/${aiProvider}`, { method: 'DELETE' });
      const d = await r.json();
      if (d.ok) {
        setAiStatus('✅ Đã xoá key');
        const cRes = await api('/api/ai/config');
        setAiConfig(await cRes.json());
      } else {
        setAiStatus('❌ ' + (d.error || 'Lỗi xoá key'));
      }
    } catch {
      setAiStatus('❌ Không kết nối được backend khi xoá key');
    }
    setTimeout(() => setAiStatus(''), 3000);
  }

  async function saveAiAuto(next: boolean) {
    setAiAutoClassify(next);
    try {
      await api('/api/ai/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: aiProvider, auto_classify: next }),
      });
    } catch {
      setAiStatus('❌ Không kết nối được backend khi lưu tự động AI');
    }
  }

  async function testAi() {
    setAiStatus('⏳ Đang test...');
    try {
      const r = await api('/api/ai/test', { method: 'POST' });
      const d = await r.json();
      setAiStatus(d.ok ? '✅ Kết nối OK!' : '❌ ' + (d.error || 'Lỗi'));
    } catch {
      setAiStatus('❌ Lỗi kết nối');
    }
    setTimeout(() => setAiStatus(''), 4000);
  }

  const suggestReply = useCallback(async (post: FbPost) => {
    setAiStatus('AI đang đọc bài viết và bình luận...');
    try {
      const r = await api('/api/ai/suggest-reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ post }),
      });
      const d = await r.json();
      if (d.ok && post.id) {
        setReplySuggestions((prev) => ({
          ...prev,
          [post.id]: { ...d.suggestion, storage: d.storage, warning: d.warning || '' },
        }));
        setAiStatus(d.storage === 'supabase' ? '✅ Đã tạo gợi ý và lưu Supabase' : '✅ Đã tạo gợi ý và lưu local');
      } else {
        setAiStatus(`❌ ${d.error || 'AI chưa tạo được gợi ý'}`);
      }
    } catch {
      setAiStatus('❌ Lỗi kết nối server');
    }
    setTimeout(() => setAiStatus(''), 7000);
  }, []);

  const summarizeComments = useCallback(async (post: FbPost) => {
    setAiStatus('AI đang đọc toàn bộ bình luận của bài viết...');
    try {
      const r = await api('/api/ai/summarize-comments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ post, force: true }),
      });
      const d = await r.json();
      if (d.ok && post.id) {
        setCommentSummaries((prev) => ({
          ...prev,
          [post.id]: { ...d.summary, storage: d.storage, warning: d.warning || '' },
        }));
        const count = d.summary?.comment_count ?? 0;
        const fetched = d.summary?.fetched_comment_count ?? 0;
        setAiStatus(
          d.storage === 'supabase'
            ? `✅ Đã đọc ${fetched}/${count} comment và lưu Supabase`
            : `✅ Đã đọc ${fetched}/${count} comment, lưu local`,
        );
      } else {
        setAiStatus(`❌ ${d.error || 'AI chưa tóm tắt được bình luận'}`);
      }
    } catch {
      setAiStatus('❌ Lỗi kết nối server');
    }
    setTimeout(() => setAiStatus(''), 9000);
  }, []);

  async function extractLeadsAll() {
    if (!allPosts.length) return;
    setLeadsBusy(true);
    setAiStatus('⏳ Đang tách lead...');
    try {
      const r = await api('/api/ai/extract-leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ posts: allPosts }),
      });
      const d = await r.json();
      if (d.ok) {
        setLeads((prev) => ({ ...prev, ...d.leads }));
        const count = Object.values(d.leads || {}).reduce(
          (sum: number, items) => sum + (items as Lead[]).length,
          0,
        );
        setAiStatus(count ? `✅ Tách được ${count} lead` : 'ℹ️ Chưa phát hiện lead');
        if (d.warning) setTimeout(() => setAiStatus(`⚠️ ${d.warning}`), 1200);
      } else {
        setAiStatus(`❌ ${d.error || 'Lỗi tách lead'}`);
      }
    } catch {
      setAiStatus('❌ Lỗi kết nối');
    }
    setLeadsBusy(false);
    setTimeout(() => setAiStatus(''), 7000);
  }

  async function classifyAll() {
    if (!allPosts.length) return;
    setClassifyBusy(true);
    try {
      const r = await api('/api/ai/classify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ posts: allPosts }),
      });
      const d = await r.json();
      if (d.ok) setClassifications((c) => ({ ...c, ...d.classifications }));
      else alert('Lỗi: ' + (d.error || 'Không xác định'));
    } catch {
      alert('Lỗi kết nối server');
    } finally {
      setClassifyBusy(false);
    }
  }

  async function login(username: string, password: string) {
    setAuthStatus('Đang đăng nhập...');
    try {
      const r = await api('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const d = await r.json();
      if (d.ok) {
        setAuthenticated(true);
        setSetupRequired(false);
        setCurrentStaff(d.staff || null);
        setAuthStatus('');
        await loadStaffCookies();
        await loadTodayCommentStats();
      } else {
        setAuthStatus(d.error || 'Sai tài khoản hoặc mật khẩu');
      }
    } catch {
      setAuthStatus('Lỗi kết nối server');
    }
  }

  async function setupFirstAccount(payload: { name: string; username: string; password: string; cookie: string }) {
    setAuthStatus('Đang tạo tài khoản...');
    try {
      const r = await api('/api/auth/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (d.ok) {
        setAuthenticated(true);
        setSetupRequired(false);
        setCurrentStaff(d.staff || null);
        setAuthStatus('');
        await loadStaffCookies();
        await loadTodayCommentStats();
      } else {
        if (d.already_setup || d.setup_required === false) {
          setSetupRequired(false);
          setAuthenticated(false);
          setCurrentStaff(null);
        }
        setAuthStatus(d.error || 'Lỗi setup');
      }
    } catch {
      setAuthStatus('Lỗi kết nối server');
    }
  }

  async function logout() {
    await api('/api/auth/logout', { method: 'POST' });
    setAuthenticated(false);
    setCurrentStaff(null);
    setStaffRows([]);
    setAllPosts([]);
    setHeaderSub('Đã đăng xuất');
  }

  async function addStaffCookie(payload: { name: string; username: string; password: string; cookie: string }) {
    if (!payload.name.trim() || !payload.username.trim() || !payload.password || !payload.cookie.trim()) {
      setStaffStatus('Nhập đủ tên, tài khoản, mật khẩu và cookie');
      return;
    }
    setStaffStatus('Đang lưu cookie...');
    try {
      const r = await api('/api/staff-cookies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (d.ok) {
        setStaffRows(d.staff || []);
        setCanManageStaff(!!d.can_manage);
        const storageText = d.storage === 'supabase' ? 'Supabase' : 'local';
        setStaffStatus(`✅ Đã lưu cookie nhân sự (${storageText})${d.warning ? ` · ${d.warning}` : ''}`);
      } else {
        setStaffStatus('❌ ' + (d.error || 'Lỗi lưu cookie'));
      }
    } catch {
      setStaffStatus('❌ Lỗi kết nối');
    }
  }

  async function deleteStaffCookie(staffId: string) {
    if (!confirm('Xoá cookie nhân sự này?')) return;
    setStaffStatus('Đang xoá...');
    try {
      const r = await api(`/api/staff-cookies/${staffId}`, { method: 'DELETE' });
      const d = await r.json();
      if (d.ok) {
        setStaffRows(d.staff || []);
        setCanManageStaff(!!d.can_manage);
        setStaffStatus('✅ Đã xoá cookie');
      } else {
        setStaffStatus('❌ ' + (d.error || 'Lỗi xoá cookie'));
      }
    } catch {
      setStaffStatus('❌ Lỗi kết nối');
    }
  }

  const masked = (aiConfig.keys_masked || {})[aiProvider] || '';
  const hasKey = Boolean(masked && masked !== '***' && masked.length > 3);
  const fbMatchedRows = fbCommentRows.filter((row) => row.is_matched);
  const tiktokMatchedRows = tiktokRows.filter((row) => row.is_matched);

  if (!authChecked) {
    return (
      <main className="auth-page">
        <div className="auth-loading">
          <img src="/st-real-logo.jpg" alt="ST.Real" />
          <div>
            <b>ST.Real Social Console</b>
            <span>Đang kiểm tra phiên đăng nhập...</span>
          </div>
        </div>
      </main>
    );
  }

  if (setupRequired || !authenticated) {
    return (
      <>
        <AuthPanel
          mode={setupRequired ? 'setup' : 'login'}
          status={authStatus}
          onLogin={login}
          onSetup={setupFirstAccount}
        />
      </>
    );
  }

  return (
    <>
      <div className="header">
        <img className="header-logo" src="/st-real-logo.jpg" alt="ST.Real" />
        <div>
          <div className="header-title">ST.Real Social Console</div>
          <div className="header-sub" title={groups.length === 1 ? `ID: ${groups[0]}` : ''}>
            {headerSub}
          </div>
        </div>
        <div className="header-spacer" />
        <div className="header-user">
          {currentStaff?.name || currentStaff?.username} · {currentStaff?.role === 'admin' ? 'admin' : 'nhân sự'}
        </div>
        <button type="button" className="header-logout" onClick={() => void logout()}>
          Đăng xuất
        </button>
      </div>

      <div className="workspace">
        <aside className="workspace-sidebar">
        <div className="panel">
          <div className="panel-label">📋 Nhóm</div>
          <div className="chips">
            {groups.map((gid) => (
              <div key={gid} className="chip chip-group" title={`${groupNames[gid] || gid}\nID: ${gid}`}>
                <span className="chip-text">{groupNames[gid] || gid}</span>
                <span className="chip-remove" onClick={() => void removeGroup(gid)} role="presentation">
                  ✕
                </span>
              </div>
            ))}
          </div>
          <div className="input-row">
            <input
              type="text"
              placeholder="ID / URL nhóm"
              value={groupInp}
              disabled={groupBusy}
              onChange={(e) => setGroupInp(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void addGroup()}
            />
            <button type="button" className="btn-add btn-add-blue" title="Thêm nhóm" onClick={() => void addGroup()}>
              +
            </button>
          </div>
        </div>

        {joinPrompt ? (
          <div className="join-prompt">
            <div className="join-prompt-icon">⚠️</div>
            <div className="join-prompt-body">
              <div className="join-prompt-title">Bạn chưa là thành viên của nhóm &quot;{joinPrompt.name}&quot;</div>
              <div className="join-prompt-sub">Cần tham gia nhóm trước thì mới theo dõi được bài viết.</div>
              <div className="join-prompt-actions">
                <button
                  type="button"
                  className="btn-join"
                  disabled={joinBusy}
                  onClick={() => void joinGroupAct(joinPrompt.id, joinPrompt.name)}
                >
                  🚀 Gửi yêu cầu tham gia
                </button>
                <a className="btn-join-fb" href={`https://www.facebook.com/groups/${joinPrompt.id}`} target="_blank" rel="noreferrer">
                  🔗 Mở trên Facebook
                </a>
                <button type="button" className="btn-join-fb" onClick={() => void forceAddGroup(joinPrompt.id, joinPrompt.name)}>
                  📋 Thêm theo dõi
                </button>
              </div>
              {joinMsg ? <div className="join-msg">{joinMsg}</div> : null}
            </div>
            <span className="join-prompt-close" onClick={() => setJoinPrompt(null)} role="presentation">
              ✕
            </span>
          </div>
        ) : null}

        <div className="panel">
          <div className="panel-label">🔍 Từ khoá</div>
          <div className="chips">
            {keywords.map((kw) => (
              <div key={kw} className="chip chip-kw">
                <span className="chip-text">{kw}</span>
                <span className="chip-remove" onClick={() => removeKw(kw)} role="presentation">
                  ✕
                </span>
              </div>
            ))}
          </div>
          <div className="input-row">
            <input
              type="text"
              placeholder="Nhập từ khoá"
              value={kwInp}
              onChange={(e) => setKwInp(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addKw()}
            />
            <button type="button" className="btn-add btn-add-orange" title="Thêm từ khoá" onClick={addKw}>
              +
            </button>
          </div>
          <div className="panel-hint">{keywords.length ? 'Chỉ hiển thị bài chứa ít nhất 1 từ khoá' : ''}</div>
        </div>

        <div className="panel">
          <div className="panel-label">✈️ Telegram</div>
          <div className="chips">
            {tgIds.map((cid) => (
              <div key={cid} className="chip chip-tg">
                <span className="chip-text">{cid}</span>
                <span className="chip-action" onClick={() => void testTg(cid)} role="presentation">
                  Test
                </span>
                <span className="chip-remove" onClick={() => void removeTg(cid)} role="presentation">
                  ✕
                </span>
              </div>
            ))}
          </div>
          <div className="input-row">
            <input
              type="text"
              placeholder="Chat ID"
              value={tgInp}
              onChange={(e) => setTgInp(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void addTg()}
            />
            <button type="button" className="btn-add btn-add-tg" title="Thêm chat ID" onClick={() => void addTg()}>
              +
            </button>
          </div>
          <div className="panel-hint">
            Nhắn <b>/start</b> cho bot Telegram của bạn để nhận Chat ID
          </div>
          <div style={{ fontSize: 12, color: '#65676b', width: '100%' }}>{tgStatus}</div>
        </div>

        <SaleSetupPanel
          aiProvider={aiProvider}
          onProviderChange={(v) => {
            setAiProvider(v);
            void onProviderChange(v);
          }}
          aiAutoClassify={aiAutoClassify}
          onAutoClassifyChange={(v) => void saveAiAuto(v)}
          aiStatus={aiStatus}
          maskedKey={masked}
          hasKey={hasKey}
          aiKeyEdit={aiKeyEdit}
          aiKeyInput={aiKeyInput}
          onAiKeyInput={setAiKeyInput}
          onToggleKeyEdit={() => setAiKeyEdit((e) => !e)}
          onTestAi={testAi}
          onSaveKey={saveAiKey}
          onDeleteKey={deleteAiKey}
          staff={staffRows}
          currentStaff={currentStaff}
          canManageStaff={canManageStaff}
          staffStatus={staffStatus}
          onAddStaff={addStaffCookie}
          onDeleteStaff={deleteStaffCookie}
        />
        </aside>

        <div className="workspace-main">
        <div className="toolbar">
          <select value={limit} onChange={(e) => setLimit(+e.target.value)}>
            <option value={5}>5 bài</option>
            <option value={10}>10 bài</option>
            <option value={20}>20 bài</option>
            <option value={50}>50 bài</option>
          </select>
          <button type="button" className="btn btn-primary" onClick={() => void loadPosts()}>
            <span className={loading ? 'ref-spin' : ''}>🔄</span> Tải lại
          </button>
          <button type="button" className="btn btn-success" onClick={openPostModal}>
            ✍️ Đăng bài
          </button>
          <button type="button" className="btn btn-classify" disabled={classifyBusy} onClick={() => void classifyAll()}>
            🤖 Phân loại
          </button>
          <button type="button" className="btn btn-leads" disabled={leadsBusy} onClick={() => void extractLeadsAll()}>
            🧲 Tách lead
          </button>
          <button
            type="button"
            className="btn btn-tiktok"
            onClick={() => {
              setTiktokModal(true);
              setTiktokStatus('');
            }}
          >
            🎵 TikTok CMT
          </button>
          <select className="cat-filter" value={catFilter} onChange={(e) => setCatFilter(e.target.value)}>
            <option value="">🏷️ Tất cả</option>
            {catOptions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <div className="interval-wrap">
            <button type="button" className={`btn btn-auto${autoOn ? ' on' : ''}`} onClick={toggleAuto}>
              {autoOn ? '⏹ Dừng' : '⏱ Tự động'}
            </button>
            <input
              type="number"
              value={intervalMin}
              min={1}
              max={60}
              disabled={autoOn}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10) || 5;
                setIntervalMin(v);
                saveSettings(autoOn, v);
              }}
            />
            <span className="unit">phút</span>
          </div>
          <div className="toolbar-spacer" />
          <span className="toolbar-status">
            ✅ Comment hôm nay: {todayCommentCount === null ? '--' : todayCommentCount}
          </span>
          <span className="toolbar-status">{toolStatus}</span>
        </div>

        <div className="feed">
          {loading && !allPosts.length ? (
            <>
              <div className="skeleton">
                <div className="skel" style={{ width: '38%', height: 13, marginBottom: 10 }} />
                <div className="skel" style={{ width: '100%', height: 11, marginBottom: 7 }} />
                <div className="skel" style={{ width: '78%', height: 11 }} />
              </div>
              <div className="skeleton">
                <div className="skel" style={{ width: '45%', height: 13, marginBottom: 10 }} />
                <div className="skel" style={{ width: '100%', height: 11, marginBottom: 7 }} />
                <div className="skel" style={{ width: '85%', height: 11 }} />
              </div>
            </>
          ) : !filteredPosts.length ? (
            <div className="empty">
              <div className="empty-icon">{feedError ? '🍪' : keywords.length || catFilter ? '🔍' : '📭'}</div>
              <div className="empty-title">
                {feedError ? 'Lỗi xác thực Facebook' : keywords.length || catFilter ? 'Không có bài khớp bộ lọc' : 'Không có bài viết nào'}
              </div>
              {feedError ? <div className="empty-sub">{feedError}</div> : null}
            </div>
          ) : (
            filteredPosts.map((p) => (
              <PostCard
                key={p.id}
                post={p}
                groupNames={groupNames}
                category={classifications[p.id]}
                keywords={keywords}
                pages={pages}
                leads={leads[p.id]}
                replySuggestion={replySuggestions[p.id]}
                commentSummary={commentSummaries[p.id]}
                onSuggestReply={suggestReply}
                onSummarizeComments={summarizeComments}
                onExploreComments={openFbCommentExplorer}
                onCommentSent={loadTodayCommentStats}
                onOpenLightbox={setLightbox}
              />
            ))
          )}
        </div>
        </div>
      </div>

      <div className={`modal-overlay${postModal ? ' open' : ''}`} onClick={(e) => e.target === e.currentTarget && setPostModal(false)} role="presentation">
        <div className="modal">
          <div className="modal-hd">
            ✍️ Đăng bài mới{' '}
            <span className="modal-close" onClick={() => setPostModal(false)} role="presentation">
              ✕
            </span>
          </div>
          <div className="field">
            <label>Nhóm (chọn nhiều nhóm)</label>
            <div className="multi-group-list">
              {groups.map((g) => (
                <div key={g} className="multi-group-item">
                  <input
                    type="checkbox"
                    id={`pg-${g}`}
                    checked={!!postSelected[g]}
                    onChange={(e) => setPostSelected((s) => ({ ...s, [g]: e.target.checked }))}
                  />
                  <label htmlFor={`pg-${g}`}>{groupNames[g] || g}</label>
                </div>
              ))}
            </div>
            <div className="multi-select-actions">
              <button type="button" onClick={() => setPostSelected(Object.fromEntries(groups.map((g) => [g, true])))}>
                Chọn tất cả
              </button>
              <button type="button" onClick={() => setPostSelected(Object.fromEntries(groups.map((g) => [g, false])))}>
                Bỏ chọn
              </button>
            </div>
          </div>
          <div className="field">
            <label>Đăng với tư cách</label>
            <select value={postPageId} onChange={(e) => setPostPageId(e.target.value)}>
              <option value="">👤 Cá nhân</option>
              {pages.map((p) => (
                <option key={p.id} value={p.id}>
                  📄 {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Nội dung</label>
            <textarea value={postContent} onChange={(e) => setPostContent(e.target.value)} placeholder="Bạn đang nghĩ gì?" />
          </div>
          <div className="modal-result">{postResult}</div>
          <div className="modal-actions">
            <button type="button" className="btn-cancel" onClick={() => setPostModal(false)}>
              Huỷ
            </button>
            <button type="button" className="btn-submit" disabled={postSubmitting} onClick={() => void submitPost()}>
              Đăng bài
            </button>
          </div>
        </div>
      </div>

      <div
        className={`modal-overlay${fbCommentModalPost ? ' open' : ''}`}
        onClick={(e) => e.target === e.currentTarget && setFbCommentModalPost(null)}
        role="presentation"
      >
        <div className="modal modal-wide">
          <div className="modal-hd">
            🔎 Lọc bình luận Facebook
            <span className="modal-close" onClick={() => setFbCommentModalPost(null)} role="presentation">
              ✕
            </span>
          </div>
          <div className="field">
            <label>Từ khoá lọc comment</label>
            <textarea
              className="keyword-textarea"
              value={fbCommentKeywords}
              onChange={(e) => setFbCommentKeywords(e.target.value)}
              placeholder="quan tâm, đặt hàng, sđt, địa chỉ"
            />
          </div>
          <div className="modal-actions modal-actions-between">
            <div className="modal-result">{fbCommentStatus}</div>
            <button type="button" className="btn-submit" disabled={fbCommentBusy} onClick={() => void fetchFacebookCommentsForFilter()}>
              {fbCommentBusy ? 'Đang đọc...' : 'Lấy & lọc CMT'}
            </button>
          </div>
          <div className="comment-filter-summary">
            Hiển thị {fbMatchedRows.length || fbCommentRows.length} comment {fbMatchedRows.length ? 'khớp từ khoá' : fbCommentRows.length ? 'đã lấy' : ''}
          </div>
          <div className="stored-comments-list">
            {(fbMatchedRows.length ? fbMatchedRows : fbCommentRows).slice(0, 100).map((row) => (
              <div key={row.comment_id} className="stored-comment">
                <div className="stored-comment-head">
                  <b>{row.author_name || 'Ẩn danh'}</b>
                  <span>{row.created_time ? new Date(row.created_time).toLocaleString('vi-VN') : ''}</span>
                </div>
                <div className="stored-comment-message">{row.message || '[Không có nội dung chữ]'}</div>
                {row.matched_keywords?.length ? (
                  <div className="stored-comment-tags">
                    {row.matched_keywords.map((kw) => (
                      <span key={kw}>{kw}</span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div
        className={`modal-overlay${tiktokModal ? ' open' : ''}`}
        onClick={(e) => e.target === e.currentTarget && setTiktokModal(false)}
        role="presentation"
      >
        <div className="modal modal-wide">
          <div className="modal-hd">
            🎵 Lọc bình luận TikTok
            <span className="modal-close" onClick={() => setTiktokModal(false)} role="presentation">
              ✕
            </span>
          </div>
          <div className="field">
            <label>Link video TikTok</label>
            <input
              className="modal-input"
              value={tiktokUrl}
              onChange={(e) => setTiktokUrl(e.target.value)}
              placeholder="https://www.tiktok.com/@user/video/..."
            />
          </div>
          <div className="field">
            <label>Từ khoá lọc comment</label>
            <textarea
              className="keyword-textarea"
              value={tiktokKeywords}
              onChange={(e) => setTiktokKeywords(e.target.value)}
              placeholder="quan tâm, đặt hàng, sđt, địa chỉ"
            />
          </div>
          <div className="modal-actions modal-actions-between">
            <div className="modal-result">{tiktokStatus}</div>
            <button type="button" className="btn-submit" disabled={tiktokBusy} onClick={() => void fetchTiktokCommentsForFilter()}>
              {tiktokBusy ? 'Đang đọc...' : 'Lấy & lọc TikTok'}
            </button>
          </div>
          <div className="comment-filter-summary">
            Hiển thị {tiktokMatchedRows.length || tiktokRows.length} comment {tiktokMatchedRows.length ? 'khớp từ khoá' : tiktokRows.length ? 'đã lấy' : ''}
          </div>
          <div className="stored-comments-list">
            {(tiktokMatchedRows.length ? tiktokMatchedRows : tiktokRows).slice(0, 100).map((row) => (
              <div key={row.comment_id} className="stored-comment">
                <div className="stored-comment-head">
                  <b>{row.author_name || 'Ẩn danh'}</b>
                  <span>{row.created_time ? new Date(row.created_time).toLocaleString('vi-VN') : ''}</span>
                </div>
                <div className="stored-comment-message">{row.message || '[Không có nội dung chữ]'}</div>
                {row.matched_keywords?.length ? (
                  <div className="stored-comment-tags">
                    {row.matched_keywords.map((kw) => (
                      <span key={kw}>{kw}</span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={`lightbox${lightbox ? ' open' : ''}`} onClick={() => setLightbox(null)} role="presentation">
        <span className="lightbox-close" onClick={() => setLightbox(null)} role="presentation">
          ✕
        </span>
        {lightbox ? <img src={lightbox} alt="" onClick={(e) => e.stopPropagation()} /> : null}
      </div>
    </>
  );
}
