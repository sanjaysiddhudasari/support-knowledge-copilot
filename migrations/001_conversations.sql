-- Persistent conversation storage for Support Knowledge Copilot.
--
-- Run this migration once against the existing Supabase Postgres database
-- (SQL editor, or `psql "$SUPABASE_DB_URL" -f migrations/001_conversations.sql`).
-- It is additive: it does not touch the existing `profiles` table or any
-- other object, so a re-run against a database that already has these tables
-- fails loudly instead of corrupting anything.
--
-- Ownership model
-- ---------------
-- The FastAPI backend talks to Postgres with the service-role key
-- (`supabase_admin`), which BYPASSES row-level security. Ownership is therefore
-- enforced in application code (`ConversationService`): every lookup is scoped
-- to the authenticated user and a conversation owned by someone else is
-- reported as "not found". The policies below are defence in depth for any
-- client that talks to PostgREST directly with a user JWT.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table conversations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    title text not null default 'New Chat',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null
        references conversations(id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    query_id text,
    confidence double precision,
    answerable boolean,
    citations jsonb,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Sidebar query: newest activity first, per user.
create index idx_conversations_user_updated
    on conversations (user_id, updated_at desc);

-- Chronological message reads for one conversation.
create index idx_messages_conversation_created
    on messages (conversation_id, created_at);

-- Idempotency: one user turn / one assistant turn per RAG request id.
create unique index idx_messages_conversation_query_role
    on messages (conversation_id, query_id, role)
    where query_id is not null;

-- ---------------------------------------------------------------------------
-- updated_at is owned by the database
-- ---------------------------------------------------------------------------
-- The application never needs to (and must not) trust a client clock: any
-- UPDATE to a conversation restamps updated_at with the server's now(). That
-- keeps "newest activity first" correct even for two writes in the same
-- millisecond.

create or replace function set_conversations_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger conversations_set_updated_at
    before update on conversations
    for each row
    execute function set_conversations_updated_at();

-- ---------------------------------------------------------------------------
-- Row-level security (defence in depth; the backend uses the service key)
-- ---------------------------------------------------------------------------

alter table conversations enable row level security;
alter table messages enable row level security;

create policy conversations_owner_read
    on conversations for select
    using (auth.uid() = user_id);

create policy conversations_owner_write
    on conversations for insert
    with check (auth.uid() = user_id);

create policy conversations_owner_update
    on conversations for update
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create policy conversations_owner_delete
    on conversations for delete
    using (auth.uid() = user_id);

create policy messages_owner_read
    on messages for select
    using (
        exists (
            select 1 from conversations c
            where c.id = messages.conversation_id
              and c.user_id = auth.uid()
        )
    );

create policy messages_owner_write
    on messages for insert
    with check (
        exists (
            select 1 from conversations c
            where c.id = messages.conversation_id
              and c.user_id = auth.uid()
        )
    );

create policy messages_owner_delete
    on messages for delete
    using (
        exists (
            select 1 from conversations c
            where c.id = messages.conversation_id
              and c.user_id = auth.uid()
        )
    );
