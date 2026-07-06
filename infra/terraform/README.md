# infra/terraform

IaC de la base AWS del entorno **dev** (T-1.15). Cuenta `634882473845` · región
`us-east-2` · profile `takab-dev`.

## Layout

```
bootstrap/   # backend remoto: bucket takab-tfstate-<account> (SSE-S3, versionado)
             # + tabla de lock takab-tflock. Estado LOCAL; se aplica UNA vez.
envs/dev/    # entorno dev completo; estado remoto en env/dev.tfstate
modules/     # network, kms, storage, messaging, database, identity,
             # registry, iot-core, iot-gateway, ci-oidc
```

## Orden de apply

1. `terraform -chdir=infra/terraform/bootstrap init && terraform -chdir=infra/terraform/bootstrap apply` (solo la primera vez).
2. `terraform -chdir=infra/terraform/envs/dev init && terraform -chdir=infra/terraform/envs/dev apply`
3. Verificación de aceptación: `infra/scripts/verify_infra.sh`

## Destroy (checklist)

1. `terraform -chdir=infra/terraform/envs/dev destroy`
2. Verificar restos con
   `aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=takab --profile takab-dev --region us-east-2`:
   solo deben quedar las llaves KMS en *pending deletion* (ventana de 7 días —
   esperado) y los recursos de bootstrap.
3. `bootstrap/` NO se destruye: guarda el estado de los entornos.
4. Retirar a mano el thing manual `Raspberry_Pruebas` (no lo gestiona Terraform).

## Costos (aprox)

- Encendido: ~$30–35 USD/mes (EC2 `t4g.small` + EBS + snapshots; IoT/SQS/S3 marginales en dev).
- Con la instancia DB detenida (`make cloud-stop`): ~$10–12 USD/mes.
- Presupuesto mensual de $50 USD con alertas al 80% (gasto real) y 100% (proyectado).

## Acceso a la DB (sin puertos públicos: túnel SSM)

```sh
make db-tunnel
# equivalente a:
aws ssm start-session --target <db_instance_id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<db_private_ip>"],"portNumber":["5432"],"localPortNumber":["5434"]}' \
  --profile takab-dev --region us-east-2
# luego: psql -h localhost -p 5434 -U postgres takab
```

Passwords en Secrets Manager: `takab/dev/db/{superuser,migrator,app,ingest}`.

## Provisionar un gateway

```sh
infra/scripts/provision_gateway.sh gw-dev-0001              # escribe ./certs-gw-dev-0001/
infra/scripts/provision_gateway.sh gw-dev-0001 takab-pi5    # instala en /etc/takab del Pi
```

## Decisiones

- **[DECISION] DB en EC2, no RDS:** RDS PostgreSQL no soporta la extensión
  `timescaledb`. Se ratifica EC2 `t4g.small` (arm64) con Docker
  `timescale/timescaledb-ha:pg16`, volumen EBS dedicado en `/data`, snapshots
  DLM diarios (03:00 UTC, retención 7) y `pg_dump` nocturno a S3 (retención 60 días).
- **[DECISION] Lock del estado:** lockfile nativo de S3 (`use_lockfile`,
  Terraform >= 1.10) + tabla DynamoDB `takab-tflock` en paralelo durante la transición.
- **CI:** el job `infra` solo hace `fmt` + `validate` (hermético, sin credenciales).
  El plan-only con el rol OIDC `takab-ci-plan` (output `ci_role_arn`) queda como
  paso opcional posterior: agregar `permissions: id-token: write` al job y un paso
  de `terraform plan` autenticado con `aws-actions/configure-aws-credentials`.
