'use client';

import type { CommentLog } from '@/lib/types';

export function HistoryPanel({ rows, status, onReload }: { rows: CommentLog[]; status: string; onReload: () => Promise<void> }) {
  return (
    <section className="module-panel">
      <div className="module-head">
        <div>
          <div className="module-kicker">Lịch sử thao tác</div>
          <h2>Comment sale</h2>
        </div>
        <button type="button" className="table-icon-button" title="Tải lại" onClick={() => void onReload()}>
          ↻
        </button>
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Thời gian</th>
              <th>Nhân sự</th>
              <th>Bài viết</th>
              <th>Nội dung</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((item, idx) => (
                <tr key={`${item.id || idx}-${item.created_at || ''}`}>
                  <td>{item.created_at ? new Date(item.created_at).toLocaleString('vi-VN') : '-'}</td>
                  <td>
                    <b>{item.staff_name || item.staff_username || 'Ẩn danh'}</b>
                    <small>{item.staff_username ? `@${item.staff_username}` : item.staff_id || ''}</small>
                  </td>
                  <td className="mono-cell">{item.post_id || '-'}</td>
                  <td>{item.comment_text || item.error_message || '-'}</td>
                  <td>
                    <span className={item.status === 'success' ? 'status-pill ok' : 'status-pill fail'}>
                      {item.status === 'success' ? 'Thành công' : 'Lỗi'}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="table-empty">
                  Chưa có lịch sử thao tác
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {status ? <div className="module-status">{status}</div> : null}
    </section>
  );
}
