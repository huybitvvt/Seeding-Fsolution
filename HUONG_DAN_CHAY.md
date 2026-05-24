# Huong dan chay cho khach clone

## 1. Cai dat

```powershell
cd E:\fb-moni
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
SIMPLE_LOGIN_ONLY=true
WEB_UI_URL=http://localhost:3000
APP_SECRET_KEY=doi_chuoi_nay_thanh_chuoi_dai_ngau_nhien
```

Trong `web`, copy `web/.env.local.example` thanh `web/.env.local` neu can doi backend URL.

## 3. Tao bang Supabase

Vao Supabase Dashboard -> SQL Editor, chay file:

```text
supabase_ai_reply_suggestions.sql
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

## 5. Loi hay gap

- Neu hien `Vui long dang nhap`: dang nhap lai bang tai khoan trong bang `staff_users`.
- Neu bao chua co bang `staff_users`: chay lai file SQL trong Supabase.
- Neu Facebook bao cookie het han: cap nhat cot `cookie` cua nhan su trong bang `staff_users`.
