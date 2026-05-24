'use client';

import type { Lead } from '@/lib/types';
import { pct } from '@/lib/format';

type LeadRow = Lead & { post_id?: string };

export function LeadManagerPanel({ leads, onExtract }: { leads: Record<string, Lead[]>; onExtract: () => Promise<void> }) {
  const rows: LeadRow[] = Object.entries(leads).flatMap(([postId, items]) => (items || []).map((item) => ({ ...item, post_id: postId })));

  return (
    <section className="module-panel">
      <div className="module-head">
        <div>
          <div className="module-kicker">Lead</div>
          <h2>Khách hàng tiềm năng</h2>
        </div>
        <button type="button" className="btn-submit" onClick={() => void onExtract()}>
          Tách lead
        </button>
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Khách hàng</th>
              <th>Nhu cầu</th>
              <th>SĐT</th>
              <th>Nguồn</th>
              <th>Bài viết</th>
              <th>Độ chắc</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((item, idx) => (
                <tr key={`${item.post_id}-${idx}`}>
                  <td>
                    <b>{item.name || 'Ẩn danh'}</b>
                    <small>{item.location || item.product_or_service || ''}</small>
                  </td>
                  <td>{item.need || item.evidence || '-'}</td>
                  <td>{item.phone || '-'}</td>
                  <td>{item.source === 'post' ? 'Bài viết' : 'Bình luận'}</td>
                  <td className="mono-cell">{item.post_id || '-'}</td>
                  <td>{pct(item.confidence) || '-'}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="table-empty">
                  Chưa có lead. Bấm Tách lead sau khi tải bài viết.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
