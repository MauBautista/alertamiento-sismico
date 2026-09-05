# Deploy de la landing pública — takabailert.com

La landing vive en `landing/` (Astro estático) y se sirve desde el S3+CloudFront del
módulo `infra/terraform/modules/site`. **Terraform posee el continente** (bucket,
distribución, certificado ACM us-east-1, alias DNS); **git + este deploy poseen el
contenido**. La página histórica de T-2.156 (`envs/dev/site/index.html`) se retiró en
el mismo PR que trajo la landing; su objeto salió del estado con un `removed` block
sin destruirse.

## Desplegar

```
make landing-deploy
```

Guardas (fallan ruidosamente): rama `main` limpia y pusheada, último CI de main en
verde, sesión SSO viva. Luego: build fresco con `PUBLIC_REV=<sha>` (el pie de la
página lo muestra como `rev <sha>`), sync por clases de caché (assets inmutables
primero, HTML al final), `deploy-info.json`, poda explícita de huérfanos (reversible:
bucket versionado) e invalidación `/*`.

## Primera transición (una sola vez, con el PR de la landing ya en main)

Orden ANTI-VENTANA — el index viejo es de Terraform y el nuevo del sync; invertir
los pasos deja la portada caída o hace que un apply posterior la revierta:

1. `bash deploy/landing/deploy.sh --pre` — sube todo con su metadata correcta por
   clase EXCEPTO `index.html` (esa clave aún es de Terraform), sin podar ni
   invalidar. Usar el modo `--pre`, no un sync a mano: un sync manual dejaría los
   assets con metadata equivocada y el deploy posterior los saltaría sin corregirla.
2. `terraform -chdir=infra/terraform/envs/dev plan` — **gate duro**: debe decir
   `0 to destroy` y que `aws_s3_object.index` deja de estar gestionado (forget).
   Si dice "will be destroyed", PARAR: falta el `removed` block.
3. `terraform apply` (Mauricio; el clasificador lo niega a agentes).
4. `make landing-deploy` (el index nuevo pisa al histórico y llega la invalidación).

## Smoke de producción

```
curl -sI https://takabailert.com/ | head -1                                   # HTTP/2 200
curl -sI https://takabailert.com/ | grep -i cache-control                     # max-age=300
curl -sI https://takabailert.com/aviso-de-privacidad.html | head -1           # 200
curl -s -o /dev/null -w '%{http_code}\n' https://takabailert.com/no-existe    # 404, nunca 200
curl -s https://takabailert.com/deploy-info.json                              # rev desplegada
```

Verificar además desde un punto NO privilegiado (lección T-2.156: la primera vez se
verificó solo desde la máquina de Mauricio y el timeout de AWS no se vio).

## Rollback

- **Normal:** `git revert` → PR → CI verde → `make landing-deploy`. Git es la fuente
  de verdad; el deploy es idempotente.
- **Emergencia (sin rebuild):** el bucket está versionado. Restaurar la versión
  anterior de las claves afectadas y crear una invalidación:

  ```
  aws s3api list-object-versions --bucket <bucket> --prefix index.html \
    --query 'Versions[?IsLatest==`false`]|[0].VersionId' --output text
  aws s3api copy-object --bucket <bucket> --key index.html \
    --copy-source '<bucket>/index.html?versionId=<VERSION_ANTERIOR>' \
    --metadata-directive REPLACE --content-type 'text/html; charset=utf-8' \
    --cache-control 'public, max-age=300'
  aws cloudfront create-invalidation --distribution-id <dist> --paths '/*'
  ```

## Reglas que no se negocian

- **Nunca** `aws s3 cp/sync` manual al bucket sin `--cache-control`: un objeto sin
  metadata se cachea 86400 s en CloudFront.
- `robots.txt` / `favicon.svg` / `og-v3.png` / `sitemap.xml` **jamás** `immutable`
  (no cambian de nombre). El OG lleva la versión en el nombre (`og-v3.png`).
- El código de las rutas inexistentes es **404** (anti-espejo T-2.156); el smoke lo
  verifica con código, no mirando la página.
- La consola SOC no se toca desde aquí: son dos sistemas separados.
