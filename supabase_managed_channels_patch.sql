create table if not exists public.managed_channels (
  id text primary key,
  platform text not null,
  channel_name text not null,
  channel_type text not null,
  link text,
  target_id text,
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.managed_channels
  add column if not exists platform text,
  add column if not exists channel_name text,
  add column if not exists channel_type text,
  add column if not exists link text,
  add column if not exists target_id text,
  add column if not exists note text,
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();

update public.managed_channels
set
  platform = coalesce(nullif(platform, ''), 'facebook'),
  channel_name = coalesce(nullif(channel_name, ''), target_id, id),
  channel_type = coalesce(nullif(channel_type, ''), 'Nhóm'),
  created_at = coalesce(created_at, now()),
  updated_at = coalesce(updated_at, now());

alter table public.managed_channels
  alter column platform set not null,
  alter column channel_name set not null,
  alter column channel_type set not null,
  alter column created_at set default now(),
  alter column created_at set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null;

create index if not exists managed_channels_platform_idx
  on public.managed_channels (platform);

create index if not exists managed_channels_type_idx
  on public.managed_channels (channel_type);

alter table public.managed_channels enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'managed_channels'
      and policyname = 'allow anon select managed channels'
  ) then
    create policy "allow anon select managed channels"
    on public.managed_channels
    for select
    to anon
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'managed_channels'
      and policyname = 'allow anon insert managed channels'
  ) then
    create policy "allow anon insert managed channels"
    on public.managed_channels
    for insert
    to anon
    with check (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'managed_channels'
      and policyname = 'allow anon update managed channels'
  ) then
    create policy "allow anon update managed channels"
    on public.managed_channels
    for update
    to anon
    using (true)
    with check (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'managed_channels'
      and policyname = 'allow anon delete managed channels'
  ) then
    create policy "allow anon delete managed channels"
    on public.managed_channels
    for delete
    to anon
    using (true);
  end if;
end $$;

select pg_notify('pgrst', 'reload schema');
