create table public.demo_content_jobs (
    id uuid primary key,
    audit_id uuid not null references public.demo_audits(id) on delete cascade,
    share_token_hash text not null unique check (length(share_token_hash) = 64),
    status text not null check (status in ('approved', 'human_review_required')),
    primary_keyword text not null check (char_length(primary_keyword) between 2 and 200),
    result jsonb not null,
    report_object_path text not null unique,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    constraint demo_content_jobs_valid_expiry check (expires_at > created_at)
);

create index demo_content_jobs_audit_id_idx
    on public.demo_content_jobs (audit_id);

create index demo_content_jobs_expires_at_idx
    on public.demo_content_jobs (expires_at);

alter table public.demo_content_jobs enable row level security;
revoke all on table public.demo_content_jobs from anon, authenticated;
grant select, insert, update, delete on table public.demo_content_jobs to service_role;

comment on table public.demo_content_jobs is
    'Short-lived recruiter content results linked to an authorized demo audit.';
