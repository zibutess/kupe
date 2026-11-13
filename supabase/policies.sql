-- kupė access rules (Row Level Security). Run AFTER schema.sql.
-- Run in Supabase: SQL Editor -> New query -> paste -> Run. Safe to run more than once.
--
-- Who can do what:
--   * The website (public key)  -> only what the rules below allow.
--   * The Python backend (secret key) -> skips these rules entirely, so it must
--     always set user_id itself.

-- Turn the rules on for every table (with no rule = no access)
alter table public.chats        enable row level security;
alter table public.trips        enable row level security;
alter table public.night_trains enable row level security;
alter table public.cache        enable row level security;

-- CHATS: a signed-in user sees and changes only their own chats
drop policy if exists "own chats" on public.chats;
create policy "own chats" on public.chats
  for all to authenticated
  using      ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

-- TRIPS: a signed-in user sees and changes only their own trips
drop policy if exists "own trips" on public.trips;
create policy "own trips" on public.trips
  for all to authenticated
  using      ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

-- Shared trips: open ONE trip by its secret link (works without signing in).
-- A function instead of a read rule, so nobody can list all shared trips.
-- Returns no owner info.
create or replace function public.get_shared_trip(p_share_id text)
returns table (id uuid, title text, plan jsonb, created_at timestamptz, updated_at timestamptz)
language sql stable security definer set search_path = ''
as $$
  select t.id, t.title, t.plan, t.created_at, t.updated_at
  from public.trips t
  where t.share_id = p_share_id and t.is_shared;
$$;
revoke execute on function public.get_shared_trip(text) from public;
grant  execute on function public.get_shared_trip(text) to anon, authenticated;

-- NIGHT_TRAINS: everyone may read; only the backend (secret key) writes
drop policy if exists "anyone reads night trains" on public.night_trains;
create policy "anyone reads night trains" on public.night_trains
  for select to anon, authenticated
  using (true);

-- CACHE: no rules on purpose -> only the backend (secret key) can use it

-- Fixes a Supabase security-advisor warning for the helper from schema.sql
alter function public.set_updated_at() set search_path = '';
