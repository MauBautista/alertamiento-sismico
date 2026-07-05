#!/usr/bin/env bash
# Smoke test RLS + inmutabilidad — TAKAB schema v1.1 ([ANALISIS-00])
# Requiere: una base EFÍMERA y recién creada con db/schema.sql ya aplicado (crea roles y
# siembra datos de prueba — NO correr contra una base con datos). 18 casos; semilla de los
# tests formales de T-1.16. Conexión parametrizable por variables de entorno estándar.
set -u
export PGHOST=${PGHOST:-127.0.0.1} PGPORT=${PGPORT:-5432} PGUSER=${PGUSER:-postgres} PGDATABASE=${PGDATABASE:-takab}
PASS=0; FAIL=0
ok()   { echo "PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "FAIL  $1  (got: $2)"; FAIL=$((FAIL+1)); }
q()    { psql -X -tA -c "$1" 2>&1; }

TA=11111111-1111-1111-1111-111111111111
TB=22222222-2222-2222-2222-222222222222
SA=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
SB=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
IA=cccccccc-cccc-cccc-cccc-cccccccccccc
IB=dddddddd-dddd-dddd-dddd-dddddddddddd

# ---------- seed (superusuario: bypassa RLS) ----------
psql -X -q -v ON_ERROR_STOP=1 <<SQL
CREATE ROLE takab_app  LOGIN NOSUPERUSER;
CREATE ROLE takab_owner LOGIN NOSUPERUSER;
GRANT USAGE ON SCHEMA public TO takab_app, takab_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO takab_app;

INSERT INTO tenants (tenant_id, code, name, visibility) VALUES
  ('$TA','TKB-A','Tenant A','private'),
  ('$TB','TKB-B','Tenant B','gov_shared');
INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES
  ('$SA','$TA','A-1','Sitio A', ST_GeogFromText('POINT(-98.30 19.06)')),
  ('$SB','$TB','B-1','Sitio B', ST_GeogFromText('POINT(-99.13 19.43)'));
INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at, severity, state, trigger) VALUES
  ('$IA', gen_random_uuid(), '$TA', '$SA', now(), 'warning', 'open', 'sasmex'),
  ('$IB', gen_random_uuid(), '$TB', '$SB', now(), 'critical','open', 'local_threshold');
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) VALUES
  ('$IA','$TA','siren_on','edge:A-1');
INSERT INTO audit_log (tenant_id, actor, verb, object) VALUES ('$TA','test','seed','x');
INSERT INTO dictamens (tenant_id, incident_id, status, basis) VALUES
  ('$TA','$IA','no_inhabit_inspect','{}');
INSERT INTO seismic_events (event_id, source, detected_at) VALUES
  ('EVT-TEST-1','sasmex', now());
ALTER TABLE incidents OWNER TO takab_owner;
SQL
[ $? -eq 0 ] && ok "seed aplicado" || bad "seed aplicado" "error"

app() { psql -X -tA -c "SET ROLE takab_app; $1" 2>&1 | tail -1; }

# T1 default-deny: app sin variables de sesión no ve nada
r=$(app "SELECT count(*) FROM incidents;");            [ "$r" = "0" ] && ok "T1 default-deny incidents (app sin vars = 0 filas)" || bad "T1" "$r"
r=$(app "SELECT count(*) FROM sites;");                [ "$r" = "0" ] && ok "T1b default-deny sites" || bad "T1b" "$r"

# T2 tenant A ve solo lo suyo
r=$(app "SET app.tenant_id='$TA'; SET app.role='soc_operator'; SELECT count(*) FROM incidents;")
[ "$r" = "1" ] && ok "T2 tenant A ve exactamente 1 incidente (el suyo)" || bad "T2" "$r"
r=$(app "SET app.tenant_id='$TA'; SET app.role='soc_operator'; SELECT tenant_id FROM incidents;")
[ "$r" = "$TA" ] && ok "T2b y es el del tenant A" || bad "T2b" "$r"

# T3 tenant A no puede tocar filas de B (0 filas afectadas, sin error)
r=$(app "SET app.tenant_id='$TA'; SET app.role='soc_operator'; UPDATE incidents SET state='acked' WHERE tenant_id='$TB' RETURNING 1;")
[ "$r" = "UPDATE 0" ] && ok "T3 tenant A no alcanza filas de B (UPDATE 0)" || bad "T3" "$r"

# T4 gov_operator: lee solo gov_shared, no escribe
r=$(app "SET app.role='gov_operator'; SELECT count(*) FROM incidents;")
[ "$r" = "1" ] && ok "T4 gov ve solo tenants gov_shared (1)" || bad "T4" "$r"
r=$(app "SET app.role='gov_operator'; SELECT tenant_id FROM incidents;")
[ "$r" = "$TB" ] && ok "T4b y es el tenant gov_shared" || bad "T4b" "$r"
r=$(app "SET app.role='gov_operator'; UPDATE incidents SET state='acked' WHERE tenant_id='$TB' RETURNING 1;")
[ "$r" = "UPDATE 0" ] && ok "T4c gov NO puede escribir incidents (UPDATE 0)" || bad "T4c" "$r"
r=$(app "SET app.role='gov_operator'; INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) VALUES ('$IB','$TB','ack','user:gov') RETURNING 1;")
echo "$r" | grep -q "row-level security" && ok "T4d gov INSERT en incident_actions rechazado por RLS" || bad "T4d" "$r"

# T5 rol interno TAKAB ve todo
r=$(app "SET app.role='takab_superadmin'; SELECT count(*) FROM incidents;")
[ "$r" = "2" ] && ok "T5 takab_superadmin ve ambos tenants" || bad "T5" "$r"

# T6 inmutabilidad (incluso como superusuario: triggers no se bypassean)
r=$(q "UPDATE audit_log SET verb='tamper';");           echo "$r" | grep -q "append-only" && ok "T6 audit_log inmutable" || bad "T6" "$r"
r=$(q "UPDATE dictamens SET status='normal_operation';"); echo "$r" | grep -q "append-only" && ok "T6b dictamens inmutable" || bad "T6b" "$r"
r=$(q "DELETE FROM incident_actions;");                 echo "$r" | grep -q "append-only" && ok "T6c incident_actions inmutable" || bad "T6c" "$r"
r=$(q "DELETE FROM incidents WHERE incident_id='$IA';"); echo "$r" | grep -qE "restrict|viola|violates" && ok "T6d borrar incidente con timeline → RESTRICT" || bad "T6d" "$r"

# T7 FORCE: el owner (no-super) de incidents también queda sujeto a RLS
r=$(psql -X -tA -c "SET ROLE takab_owner; SELECT count(*) FROM incidents;" 2>&1 | tail -1)
[ "$r" = "0" ] && ok "T7 FORCE RLS aplica incluso al owner de la tabla" || bad "T7" "$r"

# T8 seismic_events: compartido entre autenticados, invisible sin contexto
r=$(app "SET app.role='soc_operator'; SELECT count(*) FROM seismic_events;")
[ "$r" = "1" ] && ok "T8 seismic_events legible con app.role seteado" || bad "T8" "$r"
r=$(app "SELECT count(*) FROM seismic_events;")
[ "$r" = "0" ] && ok "T8b e invisible sin app.role (default-deny)" || bad "T8b" "$r"

echo "----------------------------------------"
echo "RESULTADO: $PASS PASS · $FAIL FAIL"
[ "$FAIL" -eq 0 ]
