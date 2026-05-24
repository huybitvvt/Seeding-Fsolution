'use client';

import { FormEvent, useMemo, useState } from 'react';
import type { ManagedChannel } from '@/lib/types';

type Payload = {
  platform: string;
  channel_name: string;
  channel_type: string;
  link: string;
  target_id: string;
  note: string;
};

type Props = {
  channels: ManagedChannel[];
  status: string;
  busy: boolean;
  onSave: (payload: Payload, id?: string) => Promise<boolean>;
  onDelete: (id: string) => Promise<void>;
  onReload: () => Promise<void>;
};

const EMPTY: Payload = {
  platform: '',
  channel_name: '',
  channel_type: 'Nhóm',
  link: '',
  target_id: '',
  note: '',
};

const PLATFORM_OPTIONS = ['Facebook', 'TikTok', 'YouTube', 'Instagram', 'Zalo'];
const TYPE_OPTIONS = ['Page', 'Video', 'Nhóm'];

export function ChannelManagerPanel({ channels, status, busy, onSave, onDelete, onReload }: Props) {
  const [form, setForm] = useState<Payload>(EMPTY);
  const [editingId, setEditingId] = useState('');
  const [query, setQuery] = useState('');
  const [platformFilter, setPlatformFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');

  const channelOptions = useMemo(() => {
    const names = channels.map((item) => item.channel_name || '').filter(Boolean);
    return Array.from(new Set(names)).slice(0, 30);
  }, [channels]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return channels.filter((item) => {
      const haystack = [
        item.platform,
        item.channel_name,
        item.channel_type,
        item.link,
        item.target_id,
        item.note,
      ]
        .join(' ')
        .toLowerCase();
      if (q && !haystack.includes(q)) return false;
      if (platformFilter && (item.platform || '').toLowerCase() !== platformFilter.toLowerCase()) return false;
      if (typeFilter && (item.channel_type || '') !== typeFilter) return false;
      return true;
    });
  }, [channels, platformFilter, query, typeFilter]);

  function setField(key: keyof Payload, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function edit(item: ManagedChannel) {
    setEditingId(item.id || '');
    setForm({
      platform: item.platform || '',
      channel_name: item.channel_name || '',
      channel_type: item.channel_type || 'Nhóm',
      link: item.link || '',
      target_id: item.target_id || '',
      note: item.note || '',
    });
  }

  function reset() {
    setEditingId('');
    setForm(EMPTY);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const ok = await onSave(form, editingId || undefined);
    if (ok) reset();
  }

  return (
    <section className="module-panel">
      <div className="module-head">
        <div>
          <div className="module-kicker">Quản lý nhóm / kênh</div>
          <h2>Kênh theo dõi</h2>
        </div>
        <div className="module-actions">
          <button type="button" className="table-icon-button" title="Tải lại" onClick={() => void onReload()}>
            ↻
          </button>
        </div>
      </div>

      <form className="channel-form" onSubmit={submit}>
        <div className="channel-field">
          <label>Nền tảng</label>
          <input
            list="platform-options"
            value={form.platform}
            onChange={(e) => setField('platform', e.target.value)}
            placeholder="Ví dụ: TikTok"
          />
          <datalist id="platform-options">
            {PLATFORM_OPTIONS.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
        </div>
        <div className="channel-field">
          <label>Kênh</label>
          <input
            list="channel-options"
            value={form.channel_name}
            onChange={(e) => setField('channel_name', e.target.value)}
            placeholder="Tên page / nhóm / kênh"
          />
          <datalist id="channel-options">
            {channelOptions.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
        </div>
        <div className="channel-field">
          <label>Loại</label>
          <input
            list="channel-type-options"
            value={form.channel_type}
            onChange={(e) => setField('channel_type', e.target.value)}
            placeholder="Page, Video, Nhóm"
          />
          <datalist id="channel-type-options">
            {TYPE_OPTIONS.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
        </div>
        <div className="channel-field channel-field-wide">
          <label>Link</label>
          <input value={form.link} onChange={(e) => setField('link', e.target.value)} placeholder="Dán link page / video / nhóm" />
        </div>
        <div className="channel-field">
          <label>ID</label>
          <input value={form.target_id} onChange={(e) => setField('target_id', e.target.value)} placeholder="ID nếu có" />
        </div>
        <div className="channel-field channel-field-wide">
          <label>Ghi chú</label>
          <input value={form.note} onChange={(e) => setField('note', e.target.value)} placeholder="Ghi chú vận hành" />
        </div>
        <div className="channel-form-actions">
          {editingId ? (
            <button type="button" className="btn-cancel" onClick={reset}>
              Huỷ
            </button>
          ) : null}
          <button type="submit" className="btn-submit" disabled={busy}>
            {editingId ? 'Cập nhật' : '+ Thêm'}
          </button>
        </div>
      </form>

      <div className="table-toolbar">
        <div className="table-search">
          <span>⌕</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm kiếm..." />
        </div>
        <select value={platformFilter} onChange={(e) => setPlatformFilter(e.target.value)}>
          <option value="">Nền tảng</option>
          {PLATFORM_OPTIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">Loại</option>
          {TYPE_OPTIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </div>

      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Mã</th>
              <th>Nền tảng</th>
              <th>Kênh</th>
              <th>Loại</th>
              <th>Link</th>
              <th>ID</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length ? (
              filtered.map((item) => (
                <tr key={item.id}>
                  <td className="mono-cell">{item.id}</td>
                  <td>
                    <span className="platform-pill">{item.platform || '-'}</span>
                  </td>
                  <td>
                    <b>{item.channel_name || '-'}</b>
                    {item.note ? <small>{item.note}</small> : null}
                  </td>
                  <td>{item.channel_type || '-'}</td>
                  <td className="link-cell">
                    {item.link ? (
                      <a href={item.link} target="_blank" rel="noreferrer">
                        Mở link
                      </a>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="mono-cell">{item.target_id || '-'}</td>
                  <td>
                    <div className="table-actions">
                      <button type="button" title="Sửa" onClick={() => edit(item)}>
                        ✎
                      </button>
                      <button type="button" title="Xoá" className="danger" onClick={() => item.id && void onDelete(item.id)}>
                        🗑
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7} className="table-empty">
                  Chưa có kênh nào
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
