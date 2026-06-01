'use client';

import { useMemo, useState } from 'react';
import type { Lead, LeadDashboard } from '@/lib/types';
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

const statusText = Object.fromEntries(STATUSES);
const levelText = Object.fromEntries(LEVELS);

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

export function LeadManagerPanel({
  leads,
  dashboard,
  onExtract,
  onSyncPhones,
  onUpdate,
}: {
  leads: Record<string, Lead[]>;
  dashboard?: LeadDashboard;
  onExtract: () => Promise<void>;
  onSyncPhones: () => Promise<void>;
  onUpdate: (leadKey: string, patch: Partial<Lead>) => Promise<void>;
}) {
  const [query, setQuery] = useState('');
  const [level, setLevel] = useState('all');
  const [status, setStatus] = useState('all');
  const [saleDrafts, setSaleDrafts] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState('');
  const [message, setMessage] = useState('');

  const rows: LeadRow[] = useMemo(
    () => Object.entries(leads).flatMap(([postId, items]) => (items || []).map((item) => ({ ...item, post_id: item.post_id || postId }))),
    [leads],
  );

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((item) => {
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

  async function saveSale(item: LeadRow) {
    const key = item.lead_key || '';
    const value = (saleDrafts[key] ?? item.assigned_sale_name ?? '').trim();
    await patchLead(item, { assigned_sale_name: value });
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
          <small>{rates.contacted_rate ?? 0}% đã liên hệ</small>
        </div>
        <div className="lead-kpi-card hot">
          <span>Lead nóng</span>
          <b>{dashboard?.hot_count ?? 0}</b>
          <small>{dashboard?.very_hot_count ?? 0} rất nóng</small>
        </div>
        <div className="lead-kpi-card warn">
          <span>SLA cần xử lý</span>
          <b>{dashboard?.overdue_count ?? 0}</b>
          <small>Quá hạn hoặc sắp đến hạn</small>
        </div>
        <div className="lead-kpi-card">
          <span>Điểm trung bình</span>
          <b>{dashboard?.avg_score ?? 0}</b>
          <small>{rates.hot_rate ?? 0}% hot trở lên</small>
        </div>
      </div>

      <div className="lead-filter-bar">
        <div className="table-search">
          <span>⌕</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm tên, SĐT, nhu cầu, sale..." />
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
              <th>Nhu cầu</th>
              <th>SĐT</th>
              <th>Điểm / mức</th>
              <th>Trạng thái CRM</th>
              <th>Sale phụ trách</th>
              <th>SLA</th>
              <th>Nguồn</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.length ? (
              filteredRows.map((item, idx) => {
                const key = item.lead_key || `${item.post_id}-${idx}`;
                const conf = pct(item.confidence);
                const currentStatus = item.lead_status || 'new';
                const draft = saleDrafts[key] ?? item.assigned_sale_name ?? '';
                return (
                  <tr key={key}>
                    <td>
                      <b>{item.name || 'Ẩn danh'}</b>
                      <small>{item.location || item.product_or_service || 'Chưa có phân loại ngành'}</small>
                    </td>
                    <td>
                      <div className="lead-need-cell">{item.need || item.evidence || '-'}</div>
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
                      <input
                        className="lead-sale-input"
                        value={draft}
                        placeholder="Tên sale"
                        disabled={busyKey === key}
                        onChange={(e) => setSaleDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
                        onBlur={() => {
                          if (draft !== (item.assigned_sale_name || '')) void saveSale(item);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.currentTarget.blur();
                          }
                        }}
                      />
                    </td>
                    <td>
                      {item.sla_due_at ? <b>{fmtDateTime(item.sla_due_at)}</b> : '-'}
                      {item.alert_label ? <small className={`lead-alert ${item.alert_level || ''}`}>{item.alert_label}</small> : null}
                    </td>
                    <td>
                      {sourceText(item)}
                      <small className="mono-cell">{item.post_id || item.source_id || '-'}</small>
                    </td>
                    <td>
                      {(item.comment_url || item.post_url) ? (
                        <a href={item.comment_url || item.post_url} target="_blank" rel="noreferrer">
                          Mở
                        </a>
                      ) : '-'}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={9} className="table-empty">
                  Chưa có lead phù hợp. Bấm Lấy SĐT từ comment hoặc Tách lead AI sau khi tải bài/comment.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {message ? <div className="module-status">{message}</div> : null}
      <div className="lead-crm-note">
        Cột điểm đang tính theo đặc tả F-Solution: từ khóa nhu cầu, báo giá, SĐT, deadline, độ gấp, ngân sách, khớp giải pháp và phản hồi xác nhận của khách.
      </div>
    </section>
  );
}
