# Huong dan chay Phan mem Lead Hunter_F.Solution cho khach clone

## 1. Cai dat

```powershell
cd E:\Seeding-Fsolution
python -m pip install -r requirements.txt
cd web
npm install
```

## 2. Cau hinh `.env`

Copy `.env.example` thanh `.env`, sau do dien:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
SUPABASE_STAFF_TABLE=staff_users
SUPABASE_CHANNEL_TABLE=managed_channels
SIMPLE_LOGIN_ONLY=true
WEB_UI_URL=http://localhost:3000
APP_SECRET_KEY=doi_chuoi_nay_thanh_chuoi_dai_ngau_nhien
```

Trong `web`, copy `web/.env.local.example` thanh `web/.env.local` neu can doi backend URL.
Khi deploy Vercel moi, phai thay `API_PROXY_BASE_URL` bang domain backend moi, khong dung domain cua ban cu.

## 3. Tao bang Supabase

Vao Supabase Dashboard -> SQL Editor, chay file:

```text
supabase_ai_reply_suggestions.sql
```

Neu da tung chay SQL truoc do va chi muon bo sung bang kenh/group moi, chay them file:

```text
supabase_managed_channels_patch.sql
```

Sau do them tai khoan dang nhap vao bang `staff_users`:

```sql
insert into public.staff_users (name, username, password, role, cookie, enabled)
values (
  'Ten nhan su',
  'sale01',
  '123456',
  'admin',
  'dan_cookie_facebook_co_c_user_o_day',
  true
);
```

File SQL da tu tao san tai khoan test:

```text
Tai khoan: khachtest
Mat khau: 123456
```

Tai khoan test nay chua co cookie Facebook. Neu muon test doc bai/comment Facebook, cap nhat cot `cookie` trong bang `staff_users`.

Nhan su chi can dang nhap bang `username` va `password`. Cookie Facebook do admin dien trong bang `staff_users`.

## 4. Chay local

Mo 2 terminal:

```powershell
python app.py
```

```powershell
cd web
npm run dev
```

Mo:

```text
http://localhost:3000
```

## 5. Cai extension gui CMT TikTok

Phan doc/thong ke comment TikTok chay tren web. Rieng phan gui CMT len TikTok can cai Chrome extension de dung dung phien dang nhap TikTok cua khach.

```text
chrome://extensions
```

Lam theo thu tu:

1. Bat `Developer mode`.
2. Bam `Load unpacked`.
3. Chon thu muc `browser-extension`.
4. Dang nhap TikTok tren Chrome.
5. Mo web Phan mem Lead Hunter_F.Solution va bam `Gui CMT TikTok`.

Khong can dan cookie TikTok vao web de gui comment. Neu TikTok bat dang nhap lai, dang nhap truc tiep tren tab TikTok roi bam gui lai.

## 6. Loi hay gap

- Neu hien `Vui long dang nhap`: dang nhap lai bang tai khoan trong bang `staff_users`.
- Neu bao chua co bang `staff_users`: chay lai file SQL trong Supabase.
- Neu bao chua co bang `managed_channels`: chay `supabase_managed_channels_patch.sql`, doi vai giay roi tai lai trang.
- Neu Facebook bao cookie het han: cap nhat cot `cookie` cua nhan su trong bang `staff_users`.
- Neu nut `Gui CMT TikTok` bao chua thay extension: cai/bat extension, tai lai web, va dang nhap TikTok tren Chrome.

## 7. Deploy

Frontend Next.js co the deploy len Vercel. Backend Flask (`app.py`) van can mot noi chay rieng nhu VPS/Render/Railway, sau do dat `WEB_UI_URL` va CORS dung domain frontend.
