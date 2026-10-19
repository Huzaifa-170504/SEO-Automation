create table public.demo_audits (
    id uuid primary key,
    website_url text not null check (website_url ~ '^https?://'),
    share_token_hash text not null unique check (length(share_token_hash) = 64),
    status text not null check (status in ('completed')),
    pages_discovered integer not null default 0 check (pages_discovered >= 0),
    pages_crawled integer not null default 0 check (pages_crawled between 0 and 15),
    pages_failed integer not null default 0 check (pages_failed >= 0),
    issue_count integer not null default 0 check (issue_count >= 0),
    report jsonb not null,
    report_object_path text not null unique,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    constraint demo_audits_valid_expiry check (expires_at > created_at)
);

create index demo_audits_expires_at_idx
    on public.demo_audits (expires_at);

alter table public.demo_audits enable row level security;
revoke all on table public.demo_audits from anon, authenticated;
grant select, insert, update, delete on table public.demo_audits to service_role;

create table public.demo_audit_requests (
    id bigint generated always as identity primary key,
    client_hash text not null check (length(client_hash) = 64),
    created_at timestamptz not null default now()
);

create index demo_audit_requests_client_created_idx
    on public.demo_audit_requests (client_hash, created_at desc);

alter table public.demo_audit_requests enable row level security;
revoke all on table public.demo_audit_requests from anon, authenticated;
grant select, insert, delete on table public.demo_audit_requests to service_role;
grant usage, select on sequence public.demo_audit_requests_id_seq to service_role;

create or replace function public.consume_demo_audit_quota(
    p_client_hash text,
    p_limit integer,
    p_window_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    recent_count integer;
begin
    if length(p_client_hash) <> 64 then
        raise exception 'invalid client hash';
    end if;
    if p_limit < 1 or p_limit > 20 then
        raise exception 'invalid rate limit';
    end if;
    if p_window_seconds < 60 or p_window_seconds > 86400 then
        raise exception 'invalid rate limit window';
    end if;

    perform pg_advisory_xact_lock(hashtextextended(p_client_hash, 0));

    delete from public.demo_audit_requests
    where client_hash = p_client_hash
      and created_at < now() - make_interval(secs => p_window_seconds);

    select count(*)
    into recent_count
    from public.demo_audit_requests
    where client_hash = p_client_hash
      and created_at >= now() - make_interval(secs => p_window_seconds);

    if recent_count >= p_limit then
        return false;
    end if;

    insert into public.demo_audit_requests (client_hash)
    values (p_client_hash);
    return true;
end;
$$;

revoke all on function public.consume_demo_audit_quota(text, integer, integer)
    from public, anon, authenticated;
grant execute on function public.consume_demo_audit_quota(text, integer, integer)
    to service_role;

insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values (
    'seo-demo-reports',
    'seo-demo-reports',
    false,
    5242880,
    array['application/pdf']
)
on conflict (id) do update
set
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

comment on table public.demo_audits is
    'Short-lived recruiter demo results. Access is backend-only through opaque share tokens.';
comment on table public.demo_audit_requests is
    'Pseudonymous request hashes used to enforce the public demo rate limit.';
