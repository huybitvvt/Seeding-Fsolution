'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { CookieRefreshGuide } from '@/components/CookieRefreshGuide';
import type { StaffAccount } from '@/lib/types';

export type StaffPayload = {
  name: string;
  username: string;
  password: string;
  cookie: string;
};

type Props = {
  staff: StaffAccount[];
  currentStaff?: StaffAccount | null;
  canManage: boolean;
  status: string;
  title?: string;
  kicker?: string;
  onSave: (payload: StaffPayload, staffId?: string) => Promise<boolean>;
  onDelete: (staffId: string) => Promise<void>;
};

const EMPTY: StaffPayload = {
  name: '',
  username: '',
  password: '',
  cookie: '',
};

function formatDate(value?: string) {
  if (!value) return '-';
  const time = new Date(value);
  if (Number.isNaN(time.getTime())) return '-';
  return time.toLocaleString('vi-VN');
}

export function StaffCookiePanel({
  staff,
  currentStaff,
  canManage,
  status,
  title = 'Nhân sự',
  kicker = 'Quản lý tài khoản',
  onSave,
  onDelete,
}: Props) {
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState('');
  const [form, setForm] = useState<StaffPayload>(EMPTY);
  const [bridgeReady, setBridgeReady] = useState(false);
  const [cookieBridgeStatus, setCookieBridgeStatus] = useState('');

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onMessage = (event: MessageEvent) => {
      if (event.source !== window) return;
      const data = event.data || {};
      if (data.source !== 'streal-tiktok-extension') return;
      if (data.type === 'STREAL_TIKTOK_BRIDGE_READY') {
        setBridgeReady(true);
      }
    };
    window.addEventListener('message', onMessage);
    window.postMessage(
      {
        source: 'streal-web-page',
        type: 'STREAL_TIKTOK_BRIDGE_PING',
        requestId: `staff_cookie_ping_${Date.now()}`,
      },
      window.location.origin,
    );
    return () => window.removeEventListener('message', onMessage);
  }, []);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return staff.filter((item) => {
      const haystack = [item.name, item.username, item.role, item.facebook_user_id, item.cookie_masked].join(' ').toLowerCase();
      if (q && !haystack.includes(q)) return false;
      if (roleFilter && (item.role || 'staff') !== roleFilter) return false;
      return true;
    });
  }, [query, roleFilter, staff]);

  function setField(key: keyof StaffPayload, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function resetModal() {
    setEditingId('');
    setForm(EMPTY);
    setModalOpen(false);
  }

  function openAdd() {
    setEditingId('');
    setForm(EMPTY);
    setModalOpen(true);
  }

  function openEdit(item: StaffAccount) {
    setEditingId(item.id || '');
    setForm({
      name: item.name || '',
      username: item.username || '',
      password: '',
      cookie: '',
    });
    setModalOpen(true);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const ok = await onSave(form, editingId || undefined);
    if (ok) resetModal();
  }

  function getFacebookCookieFromChrome() {
    if (typeof window === 'undefined') return;
    setCookieBridgeStatus('Đang lấy cookie Facebook từ Chrome...');
    const requestId = `fb_cookie_${Date.now()}`;
    const timer = window.setTimeout(() => {
      window.removeEventListener('message', onMessage);
      setCookieBridgeStatus('Không thấy extension phản hồi. Hãy cài/cập nhật Lead Hunter_F.Solution Bridge rồi thử lại.');
    }, 12000);

    function onMessage(event: MessageEvent) {
      if (event.source !== window) return;
      const data = event.data || {};
      if (data.source !== 'streal-tiktok-extension' || data.type !== 'STREAL_FACEBOOK_COOKIE_RESPONSE' || data.requestId !== requestId) return;
      window.clearTimeout(timer);
      window.removeEventListener('message', onMessage);
      if (data.ok && data.cookie) {
        setField('cookie', data.cookie);
        setCookieBridgeStatus(`Đã lấy cookie Facebook từ Chrome${data.c_user ? ` · c_user=${data.c_user}` : ''}.`);
      } else {
        setCookieBridgeStatus(data.error || 'Không lấy được cookie Facebook từ Chrome.');
      }
    }

    window.addEventListener('message', onMessage);
    window.postMessage(
      {
        source: 'streal-web-page',
        type: 'STREAL_FACEBOOK_COOKIE_REQUEST',
        requestId,
      },
      window.location.origin,
    );
  }

  return (
    <section className="module-panel staff-manager-panel">
      <div className="module-head">
        <div>
          <div className="module-kicker">{kicker}</div>
          <h2>{title}</h2>
        </div>
        {canManage ? (
          <button type="button" className="btn-submit" onClick={openAdd}>
            + Thêm
          </button>
        ) : null}
      </div>

      <div className="table-toolbar">
        <div className="table-search">
          <span>⌕</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm kiếm..." />
        </div>
        <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
          <option value="">Vai trò</option>
          <option value="admin">Admin</option>
          <option value="staff">Nhân sự</option>
        </select>
      </div>

      <div className="data-table-wrap">
        <table className="data-table staff-data-table">
          <thead>
            <tr>
              <th className="select-col">
                <input type="checkbox" disabled />
              </th>
              <th>Họ tên</th>
              <th>Tài khoản</th>
              <th>Vai trò</th>
              <th>Facebook ID</th>
              <th>Cookie</th>
              <th>Ngày tạo</th>
              <th>Trạng thái</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((item) => {
                const active = item.id && currentStaff?.id === item.id;
                return (
                  <tr key={item.id || item.username}>
                    <td className="select-col">
                      <input type="checkbox" disabled />
                    </td>
                    <td>
                      <b>{item.name || 'Chưa đặt tên'}</b>
                      {active ? <small>Đang đăng nhập</small> : null}
                    </td>
                    <td className="mono-cell">{item.username || '-'}</td>
                    <td>
                      <span className={item.role === 'admin' ? 'status-pill admin' : 'status-pill staff'}>
                        {item.role === 'admin' ? 'Admin' : 'Nhân sự'}
                      </span>
                    </td>
                    <td className="mono-cell">{item.facebook_user_id || '-'}</td>
                    <td>{item.cookie_masked || '-'}</td>
                    <td>{formatDate(item.created_at)}</td>
                    <td>
                      <span className={item.enabled === false ? 'status-pill fail' : 'status-pill ok'}>
                        {item.enabled === false ? 'Tắt' : 'Đang dùng'}
                      </span>
                    </td>
                    <td>
                      <div className="table-actions">
                        {canManage ? (
                          <button type="button" title="Sửa" onClick={() => openEdit(item)}>
                            ✎
                          </button>
                        ) : null}
                        {canManage && !active && item.id ? (
                          <button type="button" title="Xoá" className="danger" onClick={() => void onDelete(item.id!)}>
                            🗑
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={9} className="table-empty">
                  Chưa có nhân sự.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {status ? <div className="module-status">{status}</div> : null}
      <CookieRefreshGuide compact />
      {!canManage ? (
        <div className="module-status">
          Bạn đang đăng nhập tài khoản nhân sự. Chỉ admin được thêm, sửa, xoá nhân sự và gắn cookie.
        </div>
      ) : null}

      <div className={`modal-overlay${modalOpen ? ' open' : ''}`} onClick={(e) => e.target === e.currentTarget && resetModal()} role="presentation">
        <form className="modal staff-modal" onSubmit={submit}>
          <div className="modal-hd">
            {editingId ? 'Sửa nhân sự' : 'Thêm nhân sự'}
            <span className="modal-close" onClick={resetModal} role="presentation">
              ✕
            </span>
          </div>
          <div className="staff-modal-grid">
            <div className="field">
              <label>Tên nhân sự</label>
              <input className="modal-input" value={form.name} onChange={(e) => setField('name', e.target.value)} placeholder="Nguyễn Văn A" />
            </div>
            <div className="field">
              <label>Tài khoản đăng nhập</label>
              <input className="modal-input" value={form.username} onChange={(e) => setField('username', e.target.value)} placeholder="sale01" />
            </div>
            <div className="field">
              <label>Mật khẩu</label>
              <input
                className="modal-input"
                type="password"
                value={form.password}
                onChange={(e) => setField('password', e.target.value)}
                placeholder={editingId ? 'Để trống nếu không đổi' : 'Tối thiểu 6 ký tự'}
              />
            </div>
            <div className="field staff-cookie-field">
              <label>Cookie Facebook</label>
              <div className="staff-cookie-tools">
                <button type="button" className="btn-cancel" onClick={getFacebookCookieFromChrome}>
                  Lấy từ Chrome
                </button>
                <span>{bridgeReady ? 'Extension đã kết nối' : 'Có thể dán thủ công nếu chưa cài extension'}</span>
              </div>
              <textarea
                value={form.cookie}
                onChange={(e) => setField('cookie', e.target.value)}
                placeholder={editingId ? 'Dán cookie mới nếu cần đổi' : 'Dán cookie Facebook có c_user=...'}
              />
              {cookieBridgeStatus ? <div className="modal-result">{cookieBridgeStatus}</div> : null}
            </div>
          </div>
          <CookieRefreshGuide compact />
          <div className="modal-actions modal-actions-between">
            <div className="modal-result">{editingId ? 'Mật khẩu và cookie có thể để trống nếu không đổi.' : ''}</div>
            <div className="staff-modal-actions">
              <button type="button" className="btn-cancel" onClick={resetModal}>
                Huỷ
              </button>
              <button type="submit" className="btn-submit">
                {editingId ? 'Cập nhật' : 'Thêm'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </section>
  );
}
