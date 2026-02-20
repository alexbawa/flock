create table jobs (
    id           uuid        primary key default gen_random_uuid(),
    status       text        not null check (status in ('pending', 'running', 'complete', 'failed')),
    created_at   timestamptz not null default now(),
    completed_at timestamptz,
    submission   jsonb       not null,
    error        text
);

create table results (
    job_id uuid  not null references jobs (id) on delete cascade,
    data   jsonb not null
);
