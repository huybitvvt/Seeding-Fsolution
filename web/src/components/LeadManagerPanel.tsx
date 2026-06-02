'use client';

import { Fragment, useEffect, useMemo, useState } from 'react';
import type { Lead, LeadDashboard, SaleStaff } from '@/lib/types';
import { pct } from '@/lib/format';

type LeadRow = Lead & { post_id?: string };

const LEVELS = [
  ['all', 'Tất cả mức'],
  ['very_hot', 'Rất nóng'],
  ['hot', 'Nóng'],
  ['warm', 'Ấm'],
  ['interested', 'Quan tâm'],
  ['cold', 'Lạnh'],
];

const STATUSES = [
  ['new', 'Lead mới'],
  ['contacted', 'Đã liên hệ'],
  ['consulting', 'Đang tư vấn'],
  ['demo', 'Đã demo'],
  ['quoted', 'Đang báo giá'],
  ['won', 'Chốt deal'],
  ['lost', 'Thất bại'],
];

// Các sự kiện hành vi khách → điểm động (đặc tả Mục III)
const BEHAVIOR_EVENTS: { key: string; label: string; points: string }[] = [
  { key: 'comment_reply', label: 'KH comment', points: '+40' },
  { key: 'inbox_reply', label: 'KH inbox', points: '+50' },
  { key: 'agree_demo', label: 'Đồng ý demo', points: '+50' },
  { key: 'detail_request', label: 'Yêu cầu chi tiết', points: '+30' },
  { key: 'provided_phone', label: 'Cho SĐT', points: '+30' },
  { key: 'rejected', label: 'Từ chối', points: '-50' },
  { key: 'spam_fake', label: 'Spam/Fake', points: '-100' },
];

const levelText = Object.fromEntries(LEVELS);
const statusText = Object.fromEntries(STATUSES);

function fmtScore(value?: number) {
  const n = Number(value || 0);
  return Number.isFinite(n) ? `${Math.round(n)} điểm` : '0 điểm';
}

function fmtDateTime(value?: string) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
}

function sourceText(item: LeadRow) {
  const source = item.source === 'post' ? 'Bài viết' : 'Bình luận';
  return `${item.platform || 'facebook'} · ${source}`;
}

function moduleTags(item: LeadRow): string[] {
  const tags: string[] = [];
  (item.platform_tags || []).forEach((t) => tags.push(t));
  if (item.business_module) tags.push(item.business_module);
  if (item.industry_module) tags.push(item.industry_module);
  return Array.from(new Set(tags));
}

export function LeadManagerPanel({
  leads,
  dashboard,
  sales,
  onExtract,
  onSyncPhones,
  onUpdate,
  onAddEvent,
  onAssign,
  onAutoComment,
  onReload,
}: {
  leads: Record<string, Lead[]>;
  dashboard?: LeadDashboard;
  sales?: SaleStaff[];
  onExtract: () => Promise<void>;
  onSyncPhones: () => Promise<void>;
  onUpdate: (leadKey: string, patch: Partial<Lead>) => Promise<void>;
  onAddEvent?: (leadKey: string, event: string, note?: string) => Promise<void>;
  onAssign?: (leadKey: string, saleId: string) => Promise<void>;
  onAutoComment?: (leadKey: string) => Promise<void>;
  onReload?: () => Promise<void>;
}) {
  const [query, setQuery] = useState('');
  const [level, setLevel] = useState('all');
  const [status, setStatus] = useState('all');
  const [busyKey, setBusyKey] = useState('');
  const [message, setMessage] = useState('');
  const [expandedKey, setExpandedKey] = useState('');
  const [reloading, setReloading] = useState(false);

  // Tự tải lại lead mới nhất khi mở tab (tránh hiển thị dữ liệu cũ)
  useEffect(() => {
    if (onReload) void onReload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleReload() {
    if (!onReload) return;
    setReloading(true);
    setMessage('');
    try {
      await onReload();
      setMessage('✅ Đã làm mới danh sách lead');
    } catch {
      setMessage('❌ Không tải lại được lead');
    } finally {
      setReloading(false);
      setTimeout(() => setMessage(''), 3000);
    }
  }

  const saleList = sales || [];

  const rows: LeadRow[] = useMemo(
    () =>
      Object.entries(leads || {}).flatMap(([postId, items]) =>
        (Array.isArray(items) ? items : []).map((item) => ({ ...item, post_id: item.post_id || postId })),
      ),
    [leads],
  );

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const sorted = [...rows].sort((a, b) => Number(b.lead_score || 0) - Number(a.lead_score || 0));
    return sorted.filter((item) => {
      if (level !== 'all' && item.lead_level !== level) return false;
      if (status !== 'all' && (item.lead_status || 'new') !== status) return false;
      if (!q) return true;
      const hay = [
        item.name,
        item.phone,
        item.need,
        item.evidence,
        item.product_or_service,
        item.location,
        item.business_module,
        item.industry_module,
        item.post_id,
        item.comment_id,
        item.assigned_sale_name,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [rows, query, level, status]);

  async function patchLead(item: LeadRow, patch: Partial<Lead>) {
    const key = item.lead_key || '';
    if (!key) {
      setMessage('Lead này chưa có mã để cập nhật');
      return;
    }
    setBusyKey(key);
    setMessage('');
    try {
      await onUpdate(key, patch);
      setMessage('✅ Đã cập nhật lead');
    } catch (err) {
      setMessage(`❌ ${(err as Error).message || 'Không cập nhật được lead'}`);
    } finally {
      setBusyKey('');
      setTimeout(() => setMessage(''), 4500);
    }
  }

  async function handleEvent(item: LeadRow, event: string) {
    const key = item.lead_key || '';
    if (!key || !onAddEvent) return;
    setBusyKey(key);
    setMessage('');
    try {
      await onAddEvent(key, event);
      setMessage('✅ Đã ghi nhận hành vi khách và cập nhật điểm');
    } catch (err) {
      setMessage(`❌ ${(err as Error).message || 'Không ghi nhận được'}`);
    } finally {
      setBusyKey('');
      setTimeout(() => setMessage(''), 4500);
    }
  }

  async function handleAssign(item: LeadRow, saleId: string) {
    const key = item.lead_key || '';
    if (!key || !onAssign) return;
    setBusyKey(key);
    setMessage('');
    try {
      await onAssign(key, saleId);
      setMessage(saleId ? '✅ Đã chia lead cho sale' : '✅ Đã tự động chia lead');
    } catch (err) {
      setMessage(`❌ ${(err as Error).message || 'Không chia được lead'}`);
    } finally {
      setBusyKey('');
      setTimeout(() => setMessage(''), 4500);
    }
  }

  async function handleAutoComment(item: LeadRow) {
    const key = item.lead_key || '';
    if (!key || !onAutoComment) return;
    if (!confirm('Bot sẽ đăng comment tự động lên bài viết này bằng cookie nhân sự. Lưu ý: comment tự động có rủi ro bị Facebook hạn chế. Tiếp tục?')) return;
    setBusyKey(key);
    setMessage('');
    try {
      await onAutoComment(key);
      setMessage('✅ Bot đã đăng comment');
    } catch (err) {
      setMessage(`❌ ${(err as Error).message || 'Không gửi được comment'}`);
    } finally {
      setBusyKey('');
      setTimeout(() => setMessage(''), 5000);
    }
  }

  const rates = dashboard?.rates || {};

  return (
    <section className="module-panel lead-crm-panel">
      <div className="module-head">
        <div>
          <div className="module-kicker">Lead Hunter CRM</div>
          <h2>Khách hàng tiềm năng</h2>
        </div>
        <div className="module-actions">
          {onReload ? (
            <button type="button" className="btn-cancel" disabled={reloading} onClick={() => void handleReload()}>
              {reloading ? 'Đang tải...' : '↻ Làm mới'}
            </button>
          ) : null}
          <button type="button" className="btn-cancel" onClick={() => void onSyncPhones()}>
            Lấy SĐT từ comment
          </button>
          <button type="button" className="btn-submit" onClick={() => void onExtract()}>
            Tách lead AI
          </button>
        </div>
      </div>

      <div className="lead-kpi-grid">
        <div className="lead-kpi-card">
          <span>Tổng lead</span>
          <b>{dashboard?.total ?? rows.length}</b>
          <small>{dashboard?.new_count ?? 0} lead mới · {rates.contacted_rate ?? 0}% đã liên hệ</small>
        </div>
        <div className="lead-kpi-card hot">
          <span>Lead nóng</span>
          <b>{dashboard?.hot_count ?? 0}</b>
          <small>{dashboard?.very_hot_count ?? 0} rất nóng · {rates.hot_rate ?? 0}%</small>
        </div>
        <div className="lead-kpi-card warn">
          <span>SLA cần xử lý</span>
          <b>{dashboard?.overdue_count ?? 0}</b>
          <small>Quá hạn hoặc sắp đến hạn</small>
        </div>
        <div className="lead-kpi-card">
          <span>Điểm trung bình</span>
          <b>{dashboard?.avg_score ?? 0}</b>
          <small>Quét hôm nay: {dashboard?.scanned_today ?? 0} bài</small>
        </div>
        <div className="lead-kpi-card win">
          <span>Chốt deal</span>
          <b>{dashboard?.won_count ?? 0}</b>
          <small>{rates.won_rate ?? 0}% chốt · {rates.demo_rate ?? 0}% demo</small>
        </div>
        <div className="lead-kpi-card">
          <span>Tỷ lệ phản hồi</span>
          <b>{rates.response_rate ?? 0}%</b>
          <small>Spam {rates.spam_rate ?? 0}% · báo giá {rates.quoted_rate ?? 0}%</small>
        </div>
      </div>

      <div className="lead-filter-bar">
        <div className="table-search">
          <span>⌕</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm tên, SĐT, nhu cầu, module, sale..." />
        </div>
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          {LEVELS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="all">Tất cả trạng thái</option>
          {STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>

      <div className="data-table-wrap">
        <table className="data-table lead-crm-table">
          <thead>
            <tr>
              <th>Khách hàng</th>
              <th>Nhu cầu / Phân loại</th>
              <th>SĐT</th>
              <th>Điểm / mức</th>
              <th>Trạng thái CRM</th>
              <th>Sale phụ trách</th>
              <th>SLA</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.length ? (
              filteredRows.map((item, idx) => {
                const key = item.lead_key || `${item.post_id}-${idx}`;
                const conf = pct(item.confidence);
                const currentStatus = item.lead_status || 'new';
                const tags = moduleTags(item);
                const expanded = expandedKey === key;
                return (
                  <Fragment key={key}>
                    <tr className={expanded ? 'lead-row-active' : ''}>
                      <td>
                        <b>{item.name || 'Ẩn danh'}</b>
                        <small>{item.location || item.product_or_service || 'Chưa có phân loại ngành'}</small>
                      </td>
                      <td>
                        <div className="lead-need-cell">{item.need || item.evidence || '-'}</div>
                        {tags.length ? (
                          <div className="lead-module-tags">
                            {tags.map((t) => <span key={t} className="lead-tag">{t}</span>)}
                          </div>
                        ) : null}
                        {item.next_action ? <small className="lead-next-action">{item.next_action}</small> : null}
                      </td>
                      <td>{item.phone || '-'}</td>
                      <td>
                        <span className={`lead-score-badge level-${item.lead_level || 'cold'}`}>{fmtScore(item.lead_score)}</span>
                        <small>{item.lead_level_label || levelText[item.lead_level || 'cold'] || 'Lead lạnh'}{conf ? ` · ${conf}` : ''}</small>
                        {item.score_reasons?.length ? <small className="lead-reasons">{item.score_reasons.slice(0, 3).join(' · ')}</small> : null}
                      </td>
                      <td>
                        <select
                          className="lead-status-select"
                          value={currentStatus}
                          disabled={busyKey === key}
                          onChange={(e) => void patchLead(item, { lead_status: e.target.value })}
                        >
                          {STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                      </td>
                      <td>
                        {saleList.length ? (
                          <select
                            className="lead-sale-input"
                            value={item.assigned_sale_id || ''}
                            disabled={busyKey === key}
                            onChange={(e) => void handleAssign(item, e.target.value)}
                          >
                            <option value="">— Chưa chia —</option>
                            {saleList.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                          </select>
                        ) : (
                          <span className="lead-sale-name">{item.assigned_sale_name || 'Chưa chia'}</span>
                        )}
                      </td>
                      <td>
                        {item.sla_due_at ? <b>{fmtDateTime(item.sla_due_at)}</b> : '-'}
                        {item.alert_label ? <small className={`lead-alert ${item.alert_level || ''}`}>{item.alert_label}</small> : null}
                      </td>
                      <td>
                        <div className="lead-link-cell">
                          {(item.comment_url || item.post_url) ? (
                            <a href={item.comment_url || item.post_url} target="_blank" rel="noreferrer">Mở</a>
                          ) : <span>-</span>}
                          <button type="button" className="lead-expand-btn" onClick={() => setExpandedKey(expanded ? '' : key)}>
                            {expanded ? 'Ẩn' : 'Chi tiết'}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expanded ? (
                      <tr className="lead-detail-row">
                        <td colSpan={8}>
                          <div className="lead-detail-grid">
                            <div className="lead-detail-block">
                              <h4>Ghi nhận hành vi khách (điểm động)</h4>
                              <div className="lead-event-buttons">
                                {BEHAVIOR_EVENTS.map((ev) => (
                                  <button
                                    key={ev.key}
                                    type="button"
                                    className={`lead-event-btn ${ev.points.startsWith('-') ? 'minus' : 'plus'}`}
                                    disabled={busyKey === key || !onAddEvent}
                                    onClick={() => void handleEvent(item, ev.key)}
                                  >
                                    {ev.label} <i>{ev.points}</i>
                                  </button>
                                ))}
                              </div>
                              {onAutoComment && (item.lead_level === 'hot' || item.lead_level === 'very_hot') ? (
                                <button
                                  type="button"
                                  className="lead-bot-comment-btn"
                                  disabled={busyKey === key}
                                  onClick={() => void handleAutoComment(item)}
                                >
                                  🤖 Bot comment ngay
                                </button>
                              ) : null}
                              {item.behavior_events?.length ? (
                                <ul className="lead-event-log">
                                  {item.behavior_events.slice(-5).map((e, i) => (
                                    <li key={i}>{fmtDateTime(e.at)} · {e.type}{e.by ? ` (${e.by})` : ''}</li>
                                  ))}
                                </ul>
                              ) : <small className="muted">Chưa ghi nhận hành vi nào.</small>}
                            </div>
                            <div className="lead-detail-block">
                              <h4>Lịch sử xử lý lead</h4>
                              {item.status_history?.length ? (
                                <ul className="lead-timeline">
                                  {item.status_history.map((h, i) => (
                                    <li key={i}>
                                      <span className="lead-timeline-time">{fmtDateTime(h.at)}</span>
                                      <span className="lead-timeline-status">{statusText[h.status || 'new'] || h.status}</span>
                                      {h.note ? <small>{h.note}</small> : null}
                                      {h.by ? <small className="muted">{h.by}</small> : null}
                                    </li>
                                  ))}
                                </ul>
                              ) : <small className="muted">Chưa có thay đổi trạng thái.</small>}
                            </div>
                            <div className="lead-detail-block">
                              <h4>Chi tiết chấm điểm</h4>
                              {item.score_reasons?.length ? (
                                <ul className="lead-reason-list">
                                  {item.score_reasons.map((r, i) => <li key={i}>{r}</li>)}
                                </ul>
                              ) : <small className="muted">Chưa có lý do chấm điểm.</small>}
                              <div className="lead-detail-meta">
                                <span>Nền tảng: {(item.platform_tags || []).join(', ') || '—'}</span>
                                <span>Nghiệp vụ: {item.business_module || '—'}</span>
                                <span>Ngành: {item.industry_module || '—'}</span>
                                {item.budget ? <span>Ngân sách: {item.budget}</span> : null}
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })
            ) : (
              <tr>
                <td colSpan={8} className="table-empty">
                  Chưa có lead phù hợp. Bấm Lấy SĐT từ comment hoặc Tách lead AI sau khi tải bài/comment.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {message ? <div className="module-status">{message}</div> : null}
      <div className="lead-crm-note">
        Điểm tĩnh theo đặc tả F-Solution (từ khóa nhu cầu, báo giá, SĐT, deadline, độ gấp, ngân sách, khớp giải pháp) cộng điểm động theo hành vi khách (comment, inbox, demo, từ chối, spam). Lead nóng/rất nóng được tự động chia sale và cảnh báo SLA qua Telegram.
      </div>
    </section>
  );
}
