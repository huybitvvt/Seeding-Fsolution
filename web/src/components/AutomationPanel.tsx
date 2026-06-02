'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type AutomationSettings = {
  auto_assign_sale?: boolean;
  notify_hot_lead?: boolean;
  sla_monitor?: boolean;
  auto_comment_hot?: boolean;
  auto_comment_max_per_hour?: number;
  server_auto_scan?: boolean;
  scan_interval_min?: number;
  last_auto_scan_at?: string;
  scanned_today?: number;
};

type RunOnceResult = {
  ok?: boolean;
  error?: string;
  message?: string;
  post_count?: number;
  lead_count?: number;
  scanned_today?: number;
  last_auto_scan_at?: string;
};

function fmtTime(value?: string) {
  if (!value) return 'Chưa chạy';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
}

export function AutomationPanel() {
  const [settings, setSettings] = useState<AutomationSettings>({});
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api('/api/settings');
        const d = await r.json();
        if (!cancelled) setSettings(d || {});
      } catch {
        if (!cancelled) setStatus('Không tải được cấu hình');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(patch: Partial<AutomationSettings>) {
    const next = { ...settings, ...patch };
    setSettings(next);
    setStatus('Đang lưu...');
    try {
      const r = await api('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const d = await r.json();
      if (d.ok) setStatus('✅ Đã lưu cấu hình');
      else setStatus('❌ ' + (d.error || 'Lỗi lưu cấu hình'));
    } catch {
      setStatus('❌ Lỗi kết nối');
    }
    setTimeout(() => setStatus(''), 4000);
  }

  async function runOnce() {
    setRunning(true);
    setStatus('Đang chạy thử một vòng quét...');
    try {
      const r = await api('/api/automation/run-once', { method: 'POST' });
      const d = (await r.json()) as RunOnceResult;
      if (d.ok === false || !r.ok) {
        setStatus('❌ ' + (d.error || d.message || 'Không chạy thử được'));
        return;
      }
      setSettings((prev) => ({
        ...prev,
        scanned_today: d.scanned_today ?? prev.scanned_today,
        last_auto_scan_at: d.last_auto_scan_at ?? prev.last_auto_scan_at,
      }));
      setStatus(`✅ ${d.message || `Đã quét ${d.post_count ?? 0} bài, tách ${d.lead_count ?? 0} lead.`}`);
    } catch {
      setStatus('❌ Lỗi kết nối khi chạy thử');
    } finally {
      setRunning(false);
      setTimeout(() => setStatus(''), 6000);
    }
  }

  if (loading) {
    return <section className="module-panel"><div className="module-status">Đang tải cấu hình tự động hoá...</div></section>;
  }

  return (
    <section className="module-panel automation-panel">
      <div className="module-head">
        <div>
          <div className="module-kicker">Tự động hoá</div>
          <h2>Cấu hình Lead Hunter</h2>
        </div>
      </div>

      <div className="automation-grid">
        <div className="automation-card">
          <h3>🔄 Quét bài tự động (server)</h3>
          <p>Hệ thống tự quét các group/page đã cấu hình theo chu kỳ, kể cả khi không mở web.</p>
          <label className="automation-toggle">
            <input
              type="checkbox"
              checked={!!settings.server_auto_scan}
              onChange={(e) => void save({ server_auto_scan: e.target.checked })}
            />
            <span>Bật quét nền</span>
          </label>
          <div className="automation-field">
            <span>Chu kỳ quét (phút)</span>
            <input
              type="number"
              min={1}
              max={120}
              value={settings.scan_interval_min ?? 5}
              onChange={(e) => void save({ scan_interval_min: Math.max(1, parseInt(e.target.value, 10) || 5) })}
            />
          </div>
          <small className="automation-meta">
            Quét gần nhất: {fmtTime(settings.last_auto_scan_at)} · Hôm nay: {settings.scanned_today ?? 0} bài
          </small>
          <button className="secondary-btn" type="button" disabled={running} onClick={() => void runOnce()}>
            {running ? 'Đang quét...' : 'Chạy thử ngay'}
          </button>
        </div>

        <div className="automation-card">
          <h3>🧲 Chia lead & cảnh báo</h3>
          <p>Tự động chia lead cho sale (round-robin) và cảnh báo SLA khi lead nóng quá hạn.</p>
          <label className="automation-toggle">
            <input
              type="checkbox"
              checked={settings.auto_assign_sale !== false}
              onChange={(e) => void save({ auto_assign_sale: e.target.checked })}
            />
            <span>Tự động chia lead cho sale</span>
          </label>
          <label className="automation-toggle">
            <input
              type="checkbox"
              checked={settings.notify_hot_lead !== false}
              onChange={(e) => void save({ notify_hot_lead: e.target.checked })}
            />
            <span>Thông báo Telegram khi có lead nóng</span>
          </label>
          <label className="automation-toggle">
            <input
              type="checkbox"
              checked={settings.sla_monitor !== false}
              onChange={(e) => void save({ sla_monitor: e.target.checked })}
            />
            <span>Giám sát SLA + escalation tự động</span>
          </label>
        </div>

        <div className="automation-card danger">
          <h3>🤖 Bot comment tự động</h3>
          <p className="automation-warning">
            Cảnh báo: comment tự động hàng loạt bằng cookie nhân sự có rủi ro bị Facebook hạn chế hoặc khoá tài khoản. Chỉ bật khi đã hiểu rủi ro.
          </p>
          <label className="automation-toggle">
            <input
              type="checkbox"
              checked={!!settings.auto_comment_hot}
              onChange={(e) => void save({ auto_comment_hot: e.target.checked })}
            />
            <span>Tự động comment lead nóng/rất nóng</span>
          </label>
          <div className="automation-field">
            <span>Giới hạn comment/giờ</span>
            <input
              type="number"
              min={1}
              max={60}
              value={settings.auto_comment_max_per_hour ?? 8}
              onChange={(e) => void save({ auto_comment_max_per_hour: Math.max(1, parseInt(e.target.value, 10) || 8) })}
            />
          </div>
          <small className="automation-meta">Nội dung lấy từ gợi ý AI hoặc hồ sơ bán hàng. Chỉ áp dụng Facebook.</small>
        </div>
      </div>

      {status ? <div className="module-status">{status}</div> : null}
    </section>
  );
}
