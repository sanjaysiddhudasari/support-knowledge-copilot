-- Durable document storage for Support Knowledge Copilot.
--
-- Run once against the Supabase Postgres database, after (or with)
-- 001_conversations.sql. Additive; does not touch profiles/conversations.
--
-- The backend uses the service-role key (bypasses RLS), so ownership is
-- enforced in application code (DocumentService). RLS below is defence in
-- depth for direct PostgREST access with a user JWT.

create extension if not exists "pgcrypto";

create table documents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    filename text not null,
    storage_path text not null unique,
    file_type text not null,
    size_bytes bigint not null,
    content_hash text not null,
    version integer not null default 1,
    access_level text not null default 'public'
        check (access_level in ('public', 'internal', 'admin')),
    status text not null default 'pending'
        check (status in ('pending', 'indexing', 'ready', 'failed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index idx_documents_user_updated on documents (user_id, updated_at desc);
create unique index idx_documents_user_filename on documents (user_id, filename);

create or replace function set_documents_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger documents_set_updated_at
    before update on documents
    for each row
    execute function set_documents_updated_at();

alter table documents enable row level security;

create policy documents_owner_select on documents for select
    using (auth.uid() = user_id);
create policy documents_owner_insert on documents for insert
    with check (auth.uid() = user_id);
create policy documents_owner_update on documents for update
    using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy documents_owner_delete on documents for delete
    using (auth.uid() = user_id);
