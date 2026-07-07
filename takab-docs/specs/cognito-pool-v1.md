# Spec · AWS Cognito User Pool v1 (TAKAB Ailert)

**Estado:** materializado por T-1.15 (módulo `infra/terraform/modules/identity`).
**Consumido por:** T-1.18 (verificación de ID token + parseo de claims + propagación a RLS).
**Fuente de verdad de roles/claims:** `takab-docs/RBAC-TAKAB.md` §1/§2/§5/§7.
**Ámbito:** entorno `dev`. Verificado contra el pool real el 2026-07-06 (ver §7).

> Este documento describe lo que el pool **DEBE** tener. No es un runbook de Terraform; el DDL/HCL
> vive en `infra/terraform/modules/identity/main.tf`. Si el pool real diverge de esta spec, la
> corrección es una iteración de infra (T-1.15), no de la API.

---

## 1. Identidad del pool

| Propiedad | Valor (dev) |
|---|---|
| User Pool ID | `us-east-2_WlAWpxvnn` |
| Región | `us-east-2` |
| Nombre | `takab-dev` |
| Issuer (`iss`) | `https://cognito-idp.us-east-2.amazonaws.com/us-east-2_WlAWpxvnn` |
| JWKS | `<issuer>/.well-known/jwks.json` |
| Hosted UI domain | `takab-dev-634882473845.auth.us-east-2.amazoncognito.com` |
| Recuperación de cuenta | solo `verified_email` |
| Alta de usuarios | `admin_create_user_only = true` (sin self-signup en dev; sembrado por script) |
| Username | `email` (`username_attributes = ["email"]`, `auto_verified = ["email"]`) |
| Password policy | min 12, mayúsc + minúsc + números (símbolos opcionales) |

> Los valores concretos (pool id, client id, domain) pueden cambiar en un `terraform apply`.
> Leerlos siempre de `terraform -chdir=infra/terraform/envs/dev output` — nunca hardcodear.

---

## 2. Grupos = roles (10)

Un grupo de Cognito **por cada** rol RBAC (RBAC §1 y §5.1). El pool DEBE tener exactamente estos
10 grupos, ni más ni menos:

```
Internos TAKAB (2):  takab_superadmin · takab_support
Por tenant (7):      tenant_admin · soc_operator · inspector · building_admin ·
                     brigadista · security_guard · occupant
Gobierno (1):        gov_operator
```

El grupo llega al token en el claim `cognito:groups`. La API exige que `custom:role` ∈
`cognito:groups`; si no coincide ⇒ **401** (G3). Las **identidades máquina** (X.509 de gateway,
M2M `client_credentials`, rol DB `takab_ingest`) **no** son grupos de este pool (RBAC §1).

---

## 3. Custom attributes (claims del JWT)

5 atributos personalizados, todos `String` y **mutables** (`developer_only = false`). Se inyectan
en el **ID token** con prefijo `custom:` (ver §5).

| Atributo | Tipo | Mutable | Max length | Semántica |
|---|---|---|---|---|
| `custom:tenant_id` | String | sí | 36 | UUID del tenant → GUC `app.tenant_id` (RLS). |
| `custom:role` | String | sí | 32 | Rol RBAC; DEBE ∈ `cognito:groups`. → GUC `app.role`. |
| `custom:site_scope` | String | sí | **2048** | Alcance de sitios, **default-DENY** (ver §3.1). |
| `custom:zone_id` | String | sí | 36 | Zona/piso del ocupante (instrucción binaria). |
| `custom:surface` | String | sí | 8 | `web` \| `mobile` \| `both` → `require_web_surface`. |

> **Escritura administrada por el admin (regla de oro #5).** Aunque el esquema del pool
> los marca `mutable`, el app client SPA `takab-web` declara `write_attributes` **sin ningún
> `custom:*`**, de modo que el propio usuario **no** puede reescribirlos vía self-service
> `UpdateUserAttributes` (solo el admin, con `AdminUpdateUserAttributes`, que ignora
> `write_attributes`). Sin esa lista, el client dejaría al usuario reasignarse su
> `custom:tenant_id` a otro tenant. `claims.py` ancla RLS en `custom:tenant_id` y confía en
> este binding upstream.

### 3.1 `site_scope`: semántica default-deny y formato de cable

RBAC §5.2 lo dibuja como arreglo JSON por legibilidad, pero **el atributo Cognito es un `String`**,
así que en el token viaja como **CSV** (o `"*"`), no como array. La API (`claims.py`, G3) lo parsea:

| Valor en el token | Significado |
|---|---|
| ausente o `""` | **cero sitios** (default-DENY — [ANALISIS-00], RBAC §5.2) |
| `"*"` | todo el tenant (roles admin/soc) |
| `"uuid-a,uuid-b"` | lista explícita de sitios |

> El `max_length = 2048` es un tope duro (~50 UUIDs). RBAC §5.2 advierte **no inflar el JWT**: si un
> usuario acumula muchos sitios, dejar `"*"`/lista corta en el claim y resolver el alcance
> server-side contra `user_zone_assignments`.

---

## 4. App client `takab-web` (SPA público, PKCE)

| Propiedad | Valor requerido |
|---|---|
| Client ID (dev) | `46cndu28du7937h8m7ecsligjm` |
| Nombre | `takab-web` |
| Tipo | **público** (`generate_secret = false`, sin client secret) |
| OAuth flows | `code` (Authorization Code) — **implicit/password prohibidos** |
| OAuth scopes | `openid`, `email`, `profile` |
| Callback URL | `http://localhost:5173/auth/callback` |
| Logout URL | `http://localhost:5173/` |
| IdP soportado | `COGNITO` |
| Explicit auth flows | `ALLOW_USER_SRP_AUTH`, `ALLOW_REFRESH_TOKEN_AUTH` |
| Access token | 60 min |
| ID token | 60 min |
| Refresh token | 8 h |
| `prevent_user_existence_errors` | `ENABLED` |

### 4.1 Sobre PKCE

Cognito **no** expone un flag `PKCE` separado en `describe-user-pool-client`. PKCE (S256) queda
**implícito y obligatorio** por la combinación *client público* (sin secreto) + *authorization code
grant* vía hosted UI: un cliente público que use `code` no puede canjear el código sin
`code_verifier`. Por eso en esta spec "PKCE" = `generate_secret=false` + `allowed_oauth_flows=["code"]`.
No buscar un atributo `PKCE=true`; no existe.

---

## 5. MFA — y por qué `occupant` obliga a un pool separado (T-1.31)

### 5.1 Configuración actual (MVP web)

```
mfa_configuration = "ON"          # MFA obligatorio para TODO usuario del pool
software_token_mfa = enabled      # solo TOTP (sin SMS)
```

Correcto para el MVP: la superficie de este pool es **solo web** y los roles que pueden
activar/silenciar actuadores (RBAC §4.3: `brigadista`, `security_guard`, `building_admin`,
`inspector`, y superiores) **requieren MFA obligatorio, no negociable**. Con `ON` + TOTP se cumple.

### 5.2 El hueco: `occupant` sin MFA y la limitación de Cognito

RBAC §4.3 nota 2 y `[SUPUESTO #7]` piden **excepción de MFA para `occupant`** (se enrola por QR;
MFA universal mataría la adopción del botón de pánico). Pero **Cognito configura MFA a nivel de
pool, no por grupo**: solo hay tres estados globales — `OFF`, `OPTIONAL`, `ON`. No existe
"MFA obligatorio para el grupo X, exento para el grupo Y".

Por qué el patrón `OPTIONAL` + preferencia de usuario **NO** resuelve el hueco:

- `OPTIONAL` convierte MFA en **opt-in por usuario**. Un `brigadista` podría **declinar** el
  enrolamiento TOTP y quedarse sin segundo factor.
- Eso **viola** el requisito duro de RBAC §4.3 (MFA obligatorio para roles que tocan actuadores):
  ya no se puede *garantizar* MFA en los roles privilegiados.
- La "preferencia de MFA" solo elige el método cuando el usuario ya tiene MFA; no lo fuerza.

**Decisión (resuelta en T-1.31, fase móvil):** dos pools separados.

| Pool | MFA | Roles | Superficie |
|---|---|---|---|
| `takab-dev` (este) | `ON` (TOTP) | los 9 roles no-occupant | web |
| pool de ocupantes (T-1.31) | `OFF`/`OPTIONAL` | `occupant` | móvil |

Compensaciones para el pool sin-MFA (RBAC §4.1/§4.3): quórum de 2 ocupantes, rate-limit por
usuario/sitio, geofence del voto (GPS en el radio del sitio) y auditoría con GPS/ID. **En este
ciclo (T-1.18, web) el pool queda `ON` y no se toca**; el split es trabajo de T-1.31.

---

## 6. Validación en la API: por qué el **ID token**, no el access token

La API (T-1.18, G2) valida el **ID token** (`token_use == "id"`), no el access token. Razón dura:

- Cognito **solo inyecta los `custom:*`** (tenant_id, role, site_scope, zone_id, surface) en el
  **ID token**. El access token **no** los lleva.
- Toda la autorización de TAKAB depende de esos custom attrs (tenant para RLS, role para la matriz,
  site_scope para alcance). Sin ellos no hay tenancy → hay que leer el ID token.
- Un access token (`token_use == "access"`) presentado a la API ⇒ **401** (G2).

Chequeos que la dependencia FastAPI DEBE hacer (G2): firma **RS256** contra JWKS + `iss` == issuer
del §1 + `aud` == client id `takab-web` + `exp`/`nbf` vigentes + `token_use == "id"`. Cualquier
fallo, o `role ∉ cognito:groups`, o header ausente ⇒ **401**.

> Nota de auditoría estándar de Cognito: en el ID token, `aud` = client id y `token_use` = `"id"`;
> en el access token, no hay `aud` (hay `client_id`) y `token_use` = `"access"`. Validar `aud`
> contra el client id es coherente con exigir el ID token.

### 6.1 Estructura del claim (ejemplo, RBAC §5.2)

Ejemplo real de payload de ID token (formato de cable — `custom:site_scope` es **String CSV**, no
array; RBAC §5.2 lo dibuja como array solo por legibilidad):

```json
{
  "sub": "3f9a2c10-6b1e-4a7d-9c2f-8e5b1d0a4c11",
  "iss": "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_WlAWpxvnn",
  "aud": "46cndu28du7937h8m7ecsligjm",
  "token_use": "id",
  "auth_time": 1751760000,
  "exp": 1751763600,
  "iat": 1751760000,
  "cognito:groups": ["brigadista"],
  "custom:tenant_id": "b2d4f6a8-0c1e-4f3a-9b7c-5d2e8a1f6c40",
  "custom:role": "brigadista",
  "custom:site_scope": "a1111111-1111-1111-1111-111111111111,a2222222-2222-2222-2222-222222222222",
  "custom:zone_id": "c3333333-3333-3333-3333-333333333333",
  "custom:surface": "mobile"
}
```

Propagación a RLS dentro de la transacción del request (RBAC §5.3; helpers en `db/schema.sql §8`):

```sql
SET LOCAL app.tenant_id = '{custom:tenant_id}';
SET LOCAL app.role      = '{custom:role}';
SET LOCAL app.user_id   = '{sub}';
```

---

## 7. Verificación contra el pool real (2026-07-06, perfil `takab-dev`, us-east-2)

Cuenta AWS `634882473845`. Comandos y resultados textuales en el reporte de T-1.18 (campo `tests`).
Resumen:

| Chequeo | Esperado | Real | Resultado |
|---|---|---|---|
| Grupos | conjunto de los 10 roles | los 10 (mismo conjunto) | ✅ |
| MFA | `ON`, TOTP | `MfaConfiguration=ON`, software_token | ✅ |
| Custom attrs | 5 String mutables | tenant_id/role/zone_id 36, surface 8, site_scope 2048 | ✅ |
| App client | `takab-web` público, `code`, openid/email/profile | secreto null, flows `[code]`, scopes ok | ✅ |
| Callbacks | `localhost:5173` | callback `/auth/callback`, logout `/` | ✅ |
| Tokens | 60/60 min, 8 h | access 60m, id 60m, refresh 8h | ✅ |
| Issuer/domain | §1 | idénticos vía `terraform output` | ✅ |

**Sin discrepancias** entre esta spec y el pool real. El módulo `identity` de T-1.15 materializa la
spec completa; no requiere corrección de infra.
</content>
</invoke>
