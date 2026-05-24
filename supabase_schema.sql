-- ============================================================
-- Schema cho fb-moni  (chạy 1 lần trong Supabase → SQL Editor)
-- ============================================================

create table if not exists public.groups (
    id          text primary key,
    name        text not null default '',
    created_at  timestamptz not null default now()
);

create table if not exists public.telegram_chat_ids (
    chat_id     text primary key,
    created_at  timestamptz not null default now()
);

create table if not exists public.app_kv (
    key         text primary key,
    value       jsonb not null,
    updated_at  timestamptz not null default now()
);

create extension if not exists pgcrypto;

create table if not exists public.staff_users (
    id               text primary key default gen_random_uuid()::text,
    name             text not null,
    username         text not null,
    password         text not null,
    role             text not null default 'staff',
    cookie           text,
    facebook_user_id text,
    enabled          boolean not null default true,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create unique index if not exists staff_users_username_uidx
    on public.staff_users (username);

insert into public.staff_users (id, name, username, password, role, enabled)
values ('test-khach', 'Khách Test', 'khachtest', '123456', 'admin', true)
on conflict (username) do update
set
    name = excluded.name,
    password = excluded.password,
    role = excluded.role,
    enabled = excluded.enabled,
    updated_at = now();

create table if not exists public.seen_posts (
    post_id       text primary key,
    permalink_url text,
    group_id      text,
    author_name   text,
    message       text,
    created_time  timestamptz,
    seen_at       timestamptz not null default now()
);

-- Khi đã có bảng seen_posts từ trước, chạy các ALTER bên dưới
-- để bổ sung cột metadata (idempotent):
alter table public.seen_posts add column if not exists permalink_url text;
alter table public.seen_posts add column if not exists group_id      text;
alter table public.seen_posts add column if not exists author_name   text;
alter table public.seen_posts add column if not exists message       text;
alter table public.seen_posts add column if not exists created_time  timestamptz;

create index if not exists seen_posts_created_time_idx
    on public.seen_posts (created_time desc);
create index if not exists seen_posts_group_id_idx
    on public.seen_posts (group_id);

create table if not exists public.classifications (
    post_id     text primary key,
    category    text not null,
    updated_at  timestamptz not null default now()
);

-- ── RLS: app dùng service_role nên có thể disable cho gọn ──
alter table public.groups            disable row level security;
alter table public.telegram_chat_ids disable row level security;
alter table public.app_kv            disable row level security;
alter table public.staff_users       disable row level security;
alter table public.seen_posts        disable row level security;
alter table public.classifications   disable row level security;
