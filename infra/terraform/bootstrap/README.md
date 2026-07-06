# Bootstrap del backend remoto

Crea el bucket de estado (`takab-tfstate-<account>`) y la tabla de lock
(`takab-tflock`). Se aplica **una sola vez** con estado local:

```bash
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap apply
```

El `terraform.tfstate` local de este directorio queda **gitignored** y gestiona
solo estos 2 recursos (aceptable y estándar: nunca cambian). El resto de la
infraestructura vive en `envs/dev` con backend S3 + lock (`use_lockfile` nativo
de Terraform ≥1.10 **y** tabla DynamoDB — decisión T-1.15).

> No destruir este stack mientras exista estado en `envs/*`.
