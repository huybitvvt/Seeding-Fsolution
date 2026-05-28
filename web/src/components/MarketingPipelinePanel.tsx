'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import type { ContentPipelineArticle, ContentPipelinePost, GroupRow } from '@/lib/types';

type PipelineStats = {
  sources?: number;
  articles?: number;
  new_articles?: number;
  draft_posts?: number;
};

type PipelinePayload = {
  articles?: ContentPipelineArticle[];
  posts?: ContentPipelinePost[];
  stats?: PipelineStats;
};

type Props = {
  data: PipelinePayload;
  busy: boolean;
  status: string;
  onReload: () => Promise<void>;
  onResearch: (sourceFilter: string) => Promise<void>;
};

const FORMATS = [
  { key: 'pov', label: 'Góc nhìn' },
  { key: 'info', label: 'Tin ngắn' },
  { key: 'case', label: 'Case study' },
  { key: 'howto', label: 'How-to' },
];

export function MarketingPipelinePanel({ data, busy, status, onReload, onResearch }: Props) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [sourceFilter, setSourceFilter] = useState('all');
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [formats, setFormats] = useState<Record<string, string>>({});
  const [localStatus, setLocalStatus] = useState('');
  const [writing, setWriting] = useState(false);
  const [editingPost, setEditingPost] = useState<ContentPipelinePost | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editHashtags, setEditHashtags] = useState('');
  const [groups, setGroups] = useState<GroupRow[]>([]);
  const [publishPost, setPublishPost] = useState<ContentPipelinePost | null>(null);
  const [selectedGroups, setSelectedGroups] = useState<Record<string, boolean>>({});
  const [publishing, setPublishing] = useState(false);
  const [publishStatus, setPublishStatus] = useState('');

  const articles = data.articles || [];
  const posts = data.posts || [];
  const selectedIds = useMemo(() => Object.entries(selected).filter(([, checked]) => checked).map(([id]) => id), [selected]);
  const visibleArticles = articles.filter((item) => item.status !== 'written');

  useEffect(() => {
    api('/api/groups')
      .then((res) => res.json())
      .then((rows) => {
        const list = Array.isArray(rows) ? rows : [];
        setGroups(list);
        const checked: Record<string, boolean> = {};
        list.forEach((group: GroupRow) => {
          if (group.id) checked[group.id] = true;
        });
        setSelectedGroups(checked);
      })
      .catch(() => setGroups([]));
  }, []);

  async function runResearch() {
    await onResearch(sourceFilter);
    setStep(2);
  }

  async function writeSelected() {
    if (!selectedIds.length) {
      setLocalStatus('Chọn ít nhất một tin trước khi AI viết bài.');
      return;
    }
    setWriting(true);
    setLocalStatus('');
    try {
      const selections = selectedIds.map((id) => ({ id, format: formats[id] || 'pov' }));
      const res = await api('/api/content-pipeline/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selections }),
      });
      const payload = await res.json();
      if (!payload.ok) throw new Error(payload.error || 'AI chưa tạo được bài');
      setSelected({});
      setLocalStatus(`Đã tạo ${payload.count || 0} bản nháp.${payload.warning ? ` Lưu ý: ${payload.warning}` : ''}`);
      await onReload();
      setStep(3);
    } catch (err: any) {
      setLocalStatus('Lỗi: ' + (err?.message || 'Không tạo được content'));
    } finally {
      setWriting(false);
    }
  }

  function openEdit(post: ContentPipelinePost) {
    setEditingPost(post);
    setEditContent(post.content || '');
    setEditHashtags(post.hashtags || '');
  }

  async function savePost() {
    if (!editingPost?.id) return;
    try {
      const res = await api(`/api/content-pipeline/posts/${encodeURIComponent(editingPost.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent, hashtags: editHashtags }),
      });
      const payload = await res.json();
      if (!payload.ok) throw new Error('Không lưu được bản nháp');
      setEditingPost(null);
      setLocalStatus('Đã cập nhật bản nháp.');
      await onReload();
    } catch (err: any) {
      setLocalStatus('Lỗi: ' + (err?.message || 'Không lưu được'));
    }
  }

  async function deletePost(postId: string) {
    if (!confirm('Xoá bản nháp content này?')) return;
    await api(`/api/content-pipeline/posts/${encodeURIComponent(postId)}`, { method: 'DELETE' });
    setLocalStatus('Đã xoá bản nháp.');
    await onReload();
  }

  function openPublish(post: ContentPipelinePost) {
    setPublishPost(post);
    setPublishStatus('');
    const checked: Record<string, boolean> = {};
    groups.forEach((group) => {
      if (group.id) checked[group.id] = true;
    });
    setSelectedGroups(checked);
  }

  async function publishToGroups() {
    if (!publishPost) return;
    const targetGroups = groups.filter((group) => group.id && selectedGroups[group.id]);
    if (!targetGroups.length) {
      setPublishStatus('Chọn ít nhất một nhóm để đăng.');
      return;
    }
    const message = [publishPost.content || '', publishPost.hashtags || ''].filter(Boolean).join('\n\n').trim();
    if (!message) {
      setPublishStatus('Bản nháp chưa có nội dung.');
      return;
    }
    setPublishing(true);
    let ok = 0;
    let fail = 0;
    for (const group of targetGroups) {
      try {
        const res = await api('/api/post', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group_id: group.id, message }),
        });
        const payload = await res.json();
        if (payload.ok) ok++;
        else fail++;
      } catch {
        fail++;
      }
      setPublishStatus(`Đã đăng ${ok + fail}/${targetGroups.length} nhóm: ${ok} thành công, ${fail} lỗi.`);
    }
    if (ok > 0) {
      await api(`/api/content-pipeline/posts/${encodeURIComponent(publishPost.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'posted' }),
      });
      await onReload();
    }
    setPublishing(false);
  }

  const stepLabel = step === 1 ? 'Research' : step === 2 ? 'Lọc & chọn format' : 'Review & đăng bài';

  return (
    <section className="module-panel marketing-panel">
      <div className="module-head">
        <div>
          <div className="module-kicker">Marketing Pipeline</div>
          <h2>AI Content Pipeline</h2>
          <p className="module-subline">Cào tin thật từ nguồn RSS, chọn format, tạo bản nháp AI rồi đăng vào nhóm đang theo dõi.</p>
        </div>
        <div className="module-actions">
          <button type="button" className="btn-cancel" disabled={busy || writing} onClick={() => void onReload()}>
            Tải lại
          </button>
          <button type="button" className="btn-submit" disabled={busy || writing} onClick={() => void runResearch()}>
            {busy ? 'Đang quét...' : 'Auto-scan'}
          </button>
        </div>
      </div>

      <div className="pipeline-stepper">
        <button type="button" className={step === 1 ? 'active' : ''} onClick={() => setStep(1)}>1 Research</button>
        <span>→</span>
        <button type="button" className={step === 2 ? 'active' : ''} onClick={() => setStep(2)}>2 Lọc & Chọn Format</button>
        <span>→</span>
        <button type="button" className={step === 3 ? 'active' : ''} onClick={() => setStep(3)}>3 Review & Đăng</button>
      </div>

      <div className="pipeline-stats">
        <div><b>{data.stats?.sources || 0}</b><span>Nguồn RSS</span></div>
        <div><b>{data.stats?.articles || 0}</b><span>Tin đã lưu</span></div>
        <div><b>{data.stats?.new_articles || 0}</b><span>Tin chờ viết</span></div>
        <div><b>{data.stats?.draft_posts || 0}</b><span>Bản nháp</span></div>
      </div>

      <div className="pipeline-toolbar">
        <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
          <option value="all">Tất cả nguồn</option>
          <option value="rss">RSS / báo</option>
          <option value="techcrunch">TechCrunch</option>
          <option value="a16z">a16z</option>
          <option value="crunchbase">Crunchbase News</option>
          <option value="techstartups">TechStartups</option>
        </select>
        <div className="pipeline-current-step">{stepLabel}</div>
        {step === 2 ? (
          <button type="button" className="btn-submit" disabled={writing || busy || !selectedIds.length} onClick={() => void writeSelected()}>
            {writing ? 'AI đang viết...' : `AI viết (${selectedIds.length})`}
          </button>
        ) : null}
      </div>

      {step === 1 ? (
        <div className="pipeline-research-card">
          <h3>Research dữ liệu thật</h3>
          <p>
            Bấm Auto-scan để lấy tin mới từ TechCrunch, a16z, Crunchbase News và TechStartups. Dữ liệu sau khi quét sẽ nằm ở bước 2 để chọn format.
          </p>
          <button type="button" className="btn-submit" disabled={busy} onClick={() => void runResearch()}>
            {busy ? 'Đang lấy dữ liệu...' : 'Bắt đầu Auto-scan'}
          </button>
        </div>
      ) : step === 2 ? (
        <div className="data-table-wrap">
          <table className="data-table pipeline-table">
            <thead>
              <tr>
                <th></th>
                <th>Tin / nguồn</th>
                <th>Tóm tắt</th>
                <th>Format</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              {visibleArticles.length ? visibleArticles.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={!!selected[item.id]}
                      onChange={(e) => setSelected((prev) => ({ ...prev, [item.id]: e.target.checked }))}
                    />
                  </td>
                  <td>
                    <b>{item.title || '-'}</b>
                    <small>{item.source_name || 'RSS'} · {item.published_at ? new Date(item.published_at).toLocaleString('vi-VN') : '-'}</small>
                  </td>
                  <td>{item.summary || '-'}</td>
                  <td>
                    <select value={formats[item.id] || 'pov'} onChange={(e) => setFormats((prev) => ({ ...prev, [item.id]: e.target.value }))}>
                      {FORMATS.map((fmt) => <option key={fmt.key} value={fmt.key}>{fmt.label}</option>)}
                    </select>
                  </td>
                  <td>{item.url ? <a href={item.url} target="_blank" rel="noreferrer">Mở</a> : '-'}</td>
                </tr>
              )) : (
                <tr><td colSpan={5} className="table-empty">Chưa có tin nguồn. Quay lại bước Research và bấm Auto-scan để lấy dữ liệu thật từ RSS.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="pipeline-post-list">
          {posts.length ? posts.map((post) => (
            <article key={post.id} className="pipeline-post-card">
              <div className="pipeline-post-head">
                <div>
                  <b>{post.article_title || 'Bản nháp content'}</b>
                  <span>{post.source_name || 'Nguồn'} · {post.format || 'pov'} · {post.created_at ? new Date(post.created_at).toLocaleString('vi-VN') : '-'}</span>
                </div>
                <div className="pipeline-post-actions">
                  {post.article_url ? <a href={post.article_url} target="_blank" rel="noreferrer">Nguồn</a> : null}
                  <button type="button" onClick={() => openEdit(post)}>Sửa</button>
                  <button type="button" onClick={() => openPublish(post)}>Đăng nhóm</button>
                  <button type="button" className="danger" onClick={() => void deletePost(post.id)}>Xoá</button>
                </div>
              </div>
              <p>{post.content || '-'}</p>
              <small>{post.hashtags || ''}</small>
            </article>
          )) : (
            <div className="table-empty">Chưa có bản nháp content. Chọn tin nguồn rồi bấm AI viết.</div>
          )}
        </div>
      )}

      <div className="modal-result">{localStatus || status}</div>

      <div className={`modal-overlay${editingPost ? ' open' : ''}`}>
        <div className="modal modal-wide">
          <div className="modal-hd">
            Sửa bản nháp content
            <span className="modal-close" onClick={() => setEditingPost(null)}>×</span>
          </div>
          <div className="field">
            <label>Nội dung</label>
            <textarea value={editContent} onChange={(e) => setEditContent(e.target.value)} />
          </div>
          <div className="field">
            <label>Hashtag</label>
            <input className="modal-input" value={editHashtags} onChange={(e) => setEditHashtags(e.target.value)} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-cancel" onClick={() => setEditingPost(null)}>Huỷ</button>
            <button type="button" className="btn-submit" onClick={() => void savePost()}>Lưu</button>
          </div>
        </div>
      </div>

      <div className={`modal-overlay${publishPost ? ' open' : ''}`}>
        <div className="modal modal-wide">
          <div className="modal-hd">
            Đăng bản nháp vào nhóm
            <span className="modal-close" onClick={() => setPublishPost(null)}>×</span>
          </div>
          <div className="pipeline-publish-preview">
            <b>{publishPost?.article_title || 'Bản nháp content'}</b>
            <p>{publishPost?.content || ''}</p>
            <small>{publishPost?.hashtags || ''}</small>
          </div>
          <div className="field">
            <label>Nhóm sẽ đăng</label>
            <div className="pipeline-group-list">
              {groups.length ? groups.map((group) => (
                <label key={group.id}>
                  <input
                    type="checkbox"
                    checked={!!selectedGroups[group.id]}
                    onChange={(e) => setSelectedGroups((prev) => ({ ...prev, [group.id]: e.target.checked }))}
                  />
                  <span>{group.name || group.id}</span>
                </label>
              )) : <div className="table-empty">Chưa có nhóm theo dõi. Thêm nhóm ở module Quản lý nhóm trước.</div>}
            </div>
          </div>
          <div className="modal-actions modal-actions-between">
            <span className="modal-result">{publishStatus}</span>
            <div>
              <button type="button" className="btn-cancel" disabled={publishing} onClick={() => setPublishPost(null)}>Huỷ</button>
              <button type="button" className="btn-submit" disabled={publishing || !groups.length} onClick={() => void publishToGroups()}>
                {publishing ? 'Đang đăng...' : 'Đăng vào nhóm'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
