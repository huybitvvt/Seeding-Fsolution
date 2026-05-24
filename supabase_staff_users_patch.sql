create extension if not exists pgcrypto;

create table if not exists public.staff_users (
  id text primary key default gen_random_uuid()::text,
  name text not null,
  username text not null,
  password text not null,
  role text not null default 'staff',
  cookie text,
  facebook_user_id text,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.staff_users
  add column if not exists name text,
  add column if not exists username text,
  add column if not exists password text,
  add column if not exists role text default 'staff',
  add column if not exists cookie text,
  add column if not exists facebook_user_id text,
  add column if not exists enabled boolean default true,
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();

update public.staff_users
set
  username = coalesce(nullif(username, ''), id, 'user_' || substr(gen_random_uuid()::text, 1, 8)),
  name = coalesce(nullif(name, ''), nullif(username, ''), 'Nhan su'),
  password = coalesce(password, ''),
  role = coalesce(nullif(role, ''), 'staff'),
  enabled = coalesce(enabled, true),
  created_at = coalesce(created_at, now()),
  updated_at = coalesce(updated_at, now());

alter table public.staff_users
  alter column name set not null,
  alter column username set not null,
  alter column password set not null,
  alter column role set default 'staff',
  alter column role set not null,
  alter column enabled set default true,
  alter column enabled set not null,
  alter column created_at set default now(),
  alter column created_at set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null;

create unique index if not exists staff_users_username_uidx
  on public.staff_users (username);

create index if not exists staff_users_enabled_idx
  on public.staff_users (enabled);

alter table public.staff_users enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'staff_users'
      and policyname = 'allow anon select staff users'
  ) then
    create policy "allow anon select staff users"
    on public.staff_users
    for select
    to anon
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'staff_users'
      and policyname = 'allow anon insert staff users'
  ) then
    create policy "allow anon insert staff users"
    on public.staff_users
    for insert
    to anon
    with check (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'staff_users'
      and policyname = 'allow anon update staff users'
  ) then
    create policy "allow anon update staff users"
    on public.staff_users
    for update
    to anon
    using (true)
    with check (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'staff_users'
      and policyname = 'allow anon delete staff users'
  ) then
    create policy "allow anon delete staff users"
    on public.staff_users
    for delete
    to anon
    using (true);
  end if;
end $$;

insert into public.staff_users (
  id,
  name,
  username,
  password,
  role,
  enabled
)
values (
  'test-khach',
  'Khach Test',
  'khachtest',
  '123456',
  'admin',
  true
)
on conflict (username) do update
set
  name = excluded.name,
  password = excluded.password,
  role = excluded.role,
  enabled = excluded.enabled,
  updated_at = now();

select pg_notify('pgrst', 'reload schema');

select id, name, username, role, enabled, created_at
from public.staff_users
order by created_at desc;
