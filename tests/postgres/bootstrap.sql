-- ONLY a fresh disposable test database. These placeholders are NOT Supabase Auth.
-- Deliberately no IF NOT EXISTS: fail if any of these already exist.
set plpgsql.check_asserts=on;
begin;
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema auth;
create table auth.users(id uuid primary key);
