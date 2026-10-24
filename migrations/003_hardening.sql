-- Security hardening for Support Knowledge Copilot.
--
-- Idempotent + tolerant of a Supabase project that never installed a
-- handle_new_user trigger. Run once in the Supabase SQL editor.

-- 1) Lock down search_path on the trigger functions so they cannot be tricked
--    into resolving objects outside pg_catalog. pg_catalog is always searched
--    implicitly, so now() still resolves. (Advisor: "Function search_path").
alter function public.set_conversations_updated_at() set search_path = '';
alter function public.set_documents_updated_at() set search_path = '';

-- 2) handle_new_user is a trigger function created by Supabase's default
--    "insert user into public.profiles" trigger. It must not be callable via
--    /rest/v1/rpc by anon/authenticated/public. Tolerate its absence.
do $$
begin
    if to_regprocedure('public.handle_new_user()') is not null then
        revoke execute on function public.handle_new_user() from anon, authenticated, public;
    end if;
end $$;

-- 3) Dashboard-only (not SQL): Supabase dashboard -> Authentication ->
--    Providers/email settings. The "leaked-password protection" that rejects
--    known-breached passwords during signup is toggled in the dashboard, not
--    via RPC. Enable it there; nothing to run here.