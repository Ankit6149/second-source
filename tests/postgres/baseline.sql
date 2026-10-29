-- Run after bootstrap.sql and the UNCHANGED baseline, in the same connection.
-- Fixed synthetic identities; no application rows, network, provider or keys.
do $$
declare
  table_names text[];
  role_name text;
  privilege_name text;
  t text;
begin
  select array_agg(c.relname::text order by c.relname) into table_names
    from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname='ss' and c.relkind='r';
  assert table_names = array['approvals','artifacts','candidates','evaluations',
    'hypotheses','investigations','jobs','model_calls','observations','run_events',
    'runs','targets'], 'Unexpected baseline table set';
  assert (select count(*) from pg_constraint where connamespace='ss'::regnamespace)=104,
    'Unexpected baseline constraints';
  assert not exists(select 1 from pg_class where relnamespace='ss'::regnamespace
    and relkind='r' and not relrowsecurity), 'RLS disabled';
  assert not exists(select 1 from pg_policy where polrelid in
    (select oid from pg_class where relnamespace='ss'::regnamespace)), 'Unexpected public policy';
  foreach role_name in array array['anon','authenticated'] loop
    assert not has_schema_privilege(role_name,'ss','USAGE'), 'Unexpected schema access';
    foreach t in array table_names loop
      foreach privilege_name in array array['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'] loop
        assert not has_table_privilege(role_name,'ss.'||t,privilege_name), 'Unexpected table grant';
      end loop;
    end loop;
    for t in select relname from pg_class where relnamespace='ss'::regnamespace and relkind='S' loop
      assert not has_sequence_privilege(role_name,'ss.'||t,'USAGE')
        and not has_sequence_privilege(role_name,'ss.'||t,'SELECT')
        and not has_sequence_privilege(role_name,'ss.'||t,'UPDATE'), 'Unexpected sequence grant';
    end loop;
  end loop;
  assert has_schema_privilege('service_role','ss','USAGE');
  assert has_table_privilege('service_role','ss.run_events','SELECT')
    and has_table_privilege('service_role','ss.run_events','INSERT');
  assert not has_table_privilege('service_role','ss.run_events','UPDATE')
    and not has_table_privilege('service_role','ss.run_events','DELETE')
    and not has_table_privilege('service_role','ss.run_events','TRUNCATE');
  -- Hash columns and RLS do not implement transactional lifecycle primitives.
  assert not exists(select 1 from pg_proc where pronamespace='ss'::regnamespace);
  assert not exists(select 1 from pg_trigger where not tgisinternal and tgrelid in
    (select oid from pg_class where relnamespace='ss'::regnamespace));
end $$;

insert into auth.users values ('00000000-0000-0000-0000-000000000001'),
                              ('00000000-0000-0000-0000-000000000002');
insert into ss.targets(id,owner_id,display_name,target_kind,permission_basis)
  values ('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001',
          'NON_AI schema control','cli','Disposable test fixture');
insert into ss.investigations(id,owner_id,target_id,title,goal)
  values ('20000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001',
          '10000000-0000-0000-0000-000000000001','NON_AI schema control','Test baseline constraints');
insert into ss.runs(id,owner_id,investigation_id,origin,scope_sha256,idempotency_key)
  values ('30000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001',
          '20000000-0000-0000-0000-000000000001','mock',repeat('a',64),'NON_AI_baseline_run');

do $$
begin
  begin
    insert into ss.investigations(owner_id,target_id,title,goal)
      values ('00000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001',
              'Cross-owner control','Must fail composite ownership');
    raise exception 'Cross-owner target accepted';
  exception when foreign_key_violation then null; end;
  begin
    insert into ss.jobs(run_id,owner_id)
      values ('30000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002');
    raise exception 'Cross-owner job accepted';
  exception when foreign_key_violation then null; end;
  begin
    insert into ss.runs(owner_id,investigation_id,origin,scope_sha256,idempotency_key)
      values ('00000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001',
              'mock',repeat('a',64),'NON_AI_baseline_run');
    raise exception 'Duplicate idempotency key accepted';
  exception when unique_violation then null; end;
  begin
    insert into ss.jobs(run_id,owner_id,state)
      values ('30000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','leased');
    raise exception 'Incomplete lease accepted';
  exception when check_violation then null; end;
  begin
    insert into ss.candidates(run_id,owner_id,version,origin,candidate_sha256)
      values ('30000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001',
              1,'real',repeat('a',64));
    raise exception 'Real candidate without model call accepted';
  exception when check_violation then null; end;
  begin
    insert into ss.approvals(run_id,owner_id,action_kind,action_sha256,max_estimated_usd)
      values ('30000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001',
              'model_call',repeat('b',64),-1);
    raise exception 'Negative approval budget accepted';
  exception when check_violation then null; end;
end $$;

insert into ss.candidates(id,run_id,owner_id,version,origin,candidate_sha256)
  values ('40000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',
          '00000000-0000-0000-0000-000000000001',1,'mock',repeat('a',64));
do $$
begin
  begin
    insert into ss.evaluations(candidate_id,suite_sha256,total,passed,failed,skipped,indeterminate,result_sha256)
      values ('40000000-0000-0000-0000-000000000001',repeat('b',64),25,22,2,0,0,repeat('c',64));
    raise exception 'Inconsistent evaluation denominator accepted';
  exception when check_violation then null; end;
end $$;
insert into ss.evaluations(candidate_id,suite_sha256,total,passed,failed,skipped,indeterminate,result_sha256)
  values ('40000000-0000-0000-0000-000000000001',repeat('b',64),25,22,3,0,0,repeat('c',64));

-- Exercise actual permissions as well as catalog booleans.
set local role anon;
do $$ begin
  begin
    perform 1 from ss.runs;
    raise exception 'Anonymous read succeeded';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role authenticated;
do $$ begin
  begin
    perform 1 from ss.runs;
    raise exception 'Authenticated direct read succeeded';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role service_role;
insert into ss.run_events(run_id,owner_id,event_kind,phase,event_sha256)
  values ('30000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001',
          'NON_AI_test','capture',repeat('a',64));
do $$ begin
  assert (select count(*) from ss.run_events)=1;
  begin
    update ss.run_events set phase='modified';
    raise exception 'Service role updated event';
  exception when insufficient_privilege then null; end;
  begin
    delete from ss.run_events;
    raise exception 'Service role deleted event';
  exception when insufficient_privilege then null; end;
end $$;
reset role;

rollback;
do $$ begin
  assert not exists(select 1 from pg_namespace where nspname='ss'), 'Test DDL did not roll back';
  assert not exists(select 1 from pg_roles where rolname='service_role'), 'Test roles did not roll back';
end $$;
select 'BASELINE_CONSTRAINTS_OK / NON_AI / rolled_back' as result;
