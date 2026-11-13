-- kupė database tables. Run in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run more than once.

-- Shared helper: keeps "updated_at" current whenever a row changes
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- 1. CHATS: one conversation with the trip-planner agent
create table if not exists public.chats (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  session_id  text,                             -- Claude agent session ID (set on first message)
  title       text,                             -- e.g. first user message, for the chat list
  messages    jsonb not null default '[]',      -- [{"role": "user"|"agent", "text": "..."}]
  seen        jsonb not null default '[]',      -- event IDs already handled
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists chats_user_idx on public.chats (user_id, created_at desc);

drop trigger if exists chats_updated_at on public.chats;
create trigger chats_updated_at before update on public.chats
  for each row execute function public.set_updated_at();

-- 2. TRIPS: a finished, saved trip plan
create table if not exists public.trips (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  chat_id     uuid references public.chats(id) on delete set null,
  title       text not null,
  plan        jsonb not null,                   -- the day-by-day plan in the fixed format
  share_id    text not null unique
              default replace(gen_random_uuid()::text, '-', ''),  -- 32 random characters
  is_shared   boolean not null default false,   -- link only works when the owner turns it on
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists trips_user_idx on public.trips (user_id, created_at desc);

drop trigger if exists trips_updated_at on public.trips;
create trigger trips_updated_at before update on public.trips
  for each row execute function public.set_updated_at();

-- 3. NIGHT_TRAINS: collected once from overview pages, then reused
create table if not exists public.night_trains (
  id                bigint generated always as identity primary key,
  from_city         text not null,
  to_city           text not null,
  operator          text,                       -- e.g. "ÖBB Nightjet"
  train_name        text,
  days              text[] not null default '{}',  -- e.g. {Mon,Wed,Fri}; empty = daily/unknown
  departure_time    time,
  arrival_time      time,
  arrives_next_day  boolean not null default true,
  types             text[] not null default '{}'
                    check (types <@ array['sleeper','couchette','seat']),
  source_url        text not null,
  checked_on        date not null default current_date,
  unique (from_city, to_city, operator, departure_time)
);
create index if not exists night_trains_route_idx on public.night_trains (from_city, to_city);

-- 4. CACHE: saved results from Firecrawl and transit lookups
create table if not exists public.cache (
  key         text primary key,                 -- fingerprint of the request
  source      text not null check (source in ('firecrawl', 'transit')),
  data        jsonb not null,
  created_at  timestamptz not null default now(),
  expires_at  timestamptz                       -- null = never expires
);
create index if not exists cache_expires_idx on public.cache (expires_at);

-- Upgrade for databases created before session_id became optional:
alter table public.chats alter column session_id drop not null;
