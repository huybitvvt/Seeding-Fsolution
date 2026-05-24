'use client';

import { FormEvent, useState } from 'react';

type Props = {
  mode: 'login' | 'setup';
  status: string;
  onLogin: (username: string, password: string) => Promise<void>;
  onSetup: (payload: { name: string; username: string; password: string; cookie: string }) => Promise<void>;
};

export function AuthPanel({ mode, status, onLogin, onSetup }: Props) {
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [cookie, setCookie] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const isSetup = mode === 'setup';

  async function submit() {
    if (submitting) return;
    setSubmitting(true);
    try {
      if (isSetup) {
        await onSetup({ name, username, password, cookie });
      } else {
        await onLogin(username, password);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void submit();
  }

  return (
    <main className="auth-page">
      <section className="auth-shell">
        <div className="auth-brand">
          <div className="auth-logo-card">
            <img src="/st-real-logo.jpg" alt="ST.Real" />
          </div>
          <div className="auth-brand-copy">
            <div className="auth-kicker">ST.Real Social Console</div>
            <h1>Quản lý bình luận và chăm sóc khách hàng đa kênh</h1>
            <p>
              Theo dõi bài viết, lọc comment Facebook/TikTok, lưu lịch sử sale và hỗ trợ AI tóm tắt trong một màn hình vận hành.
            </p>
          </div>
          <div className="auth-feature-grid" aria-hidden="true">
            <div>
              <b>FB</b>
              <span>Lọc comment</span>
            </div>
            <div>
              <b>AI</b>
              <span>Tóm tắt lead</span>
            </div>
            <div>
              <b>Sale</b>
              <span>Theo dõi hiệu suất</span>
            </div>
          </div>
        </div>

        <form className="auth-card" onSubmit={onSubmit}>
          <div className="auth-form-logo">
            <img src="/st-real-logo.jpg" alt="ST.Real" />
          </div>
          <div className="auth-title">{isSetup ? 'Setup tài khoản đầu tiên' : 'Đăng nhập'}</div>
          <div className="auth-sub">
            {isSetup
              ? 'Chỉ admin khởi tạo hệ thống. Sau khi đăng nhập, admin sẽ thêm nhân sự và gắn cookie Facebook riêng cho từng người.'
              : 'Mỗi nhân sự dùng tài khoản riêng. Cookie Facebook sẽ tự gắn theo tài khoản đăng nhập.'}
          </div>
          {isSetup ? <div className="auth-admin-note">Nhân sự không tự tạo tài khoản tại bước này.</div> : null}
          {isSetup ? (
            <div className="auth-field">
              <label>Tên quản trị viên</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ví dụ: Admin ST.Real" autoComplete="name" />
            </div>
          ) : null}
          <div className="auth-field">
            <label>Tài khoản đăng nhập</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder="Nhập tài khoản" />
          </div>
          <div className="auth-field">
            <label>Mật khẩu</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={isSetup ? 'new-password' : 'current-password'}
              placeholder="Nhập mật khẩu"
            />
          </div>
          {isSetup ? (
            <div className="auth-field">
              <label>Cookie Facebook</label>
              <textarea value={cookie} onChange={(e) => setCookie(e.target.value)} placeholder="Dán cookie có c_user=..." />
            </div>
          ) : null}
          {status ? <div className="auth-status">{status}</div> : null}
          <div className="auth-actions">
            <button type="submit" className="auth-submit" disabled={submitting}>
              {submitting ? 'Đang xử lý...' : isSetup ? 'Tạo tài khoản admin' : 'Đăng nhập'}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
