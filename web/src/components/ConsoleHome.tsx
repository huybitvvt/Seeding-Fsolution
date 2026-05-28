'use client';

type ModuleKey = 'home' | 'staff' | 'channels' | 'manage' | 'cookies' | 'history' | 'leads' | 'marketing';

type Card = {
  key: ModuleKey;
  icon: string;
  title: string;
  desc: string;
  tone: string;
};

const CARDS: Card[] = [
  { key: 'staff', icon: '👥', title: 'Nhân sự', desc: 'Quản lý tài khoản sale và quyền thao tác.', tone: 'green' },
  { key: 'channels', icon: '📋', title: 'Quản lý nhóm', desc: 'Lưu nền tảng, kênh, page, video và nhóm.', tone: 'orange' },
  { key: 'manage', icon: '☑', title: 'Quản lý', desc: 'Theo dõi bài viết, phân loại và vận hành.', tone: 'blue' },
  { key: 'cookies', icon: '🍪', title: 'Cooki', desc: 'Quản lý phiên đăng nhập và cookie nhân sự.', tone: 'purple' },
  { key: 'history', icon: '🗓', title: 'Lịch thử thao tác', desc: 'Xem lịch sử comment và trạng thái thao tác.', tone: 'red' },
  { key: 'leads', icon: '◎', title: 'Lead', desc: 'Theo dõi khách hàng tiềm năng và nhu cầu.', tone: 'yellow' },
  { key: 'marketing', icon: '✦', title: 'Marketing', desc: 'Cào tin, chọn format và tạo bản nháp AI.', tone: 'blue' },
];

export function ConsoleHome({ staffName, onOpen }: { staffName?: string; onOpen: (key: ModuleKey) => void }) {
  return (
    <section className="home-view">
      <div className="home-title">
        <h1>Chào buổi tối, {staffName || 'Admin'} 👋</h1>
        <p>Chọn module để vận hành hệ thống social console.</p>
      </div>
      <div className="home-tabs">
        <button className="active" type="button">
          Chức năng
        </button>
        <button type="button">Đánh dấu</button>
        <button type="button">Tất cả</button>
      </div>
      <div className="module-card-grid">
        {CARDS.map((item) => (
          <button key={item.key} type="button" className="module-card" onClick={() => onOpen(item.key)}>
            <span className={`module-card-icon tone-${item.tone}`}>{item.icon}</span>
            <b>{item.title}</b>
            <small>{item.desc}</small>
          </button>
        ))}
      </div>
    </section>
  );
}
