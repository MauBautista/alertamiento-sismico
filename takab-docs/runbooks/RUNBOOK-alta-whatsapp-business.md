# Runbook · Alta del WhatsApp Business Account y aprobación de la plantilla

> **Ficha:** [`T-2.77.a`](../TASKS.md) · **Pendiente:** [`PENDIENTES-MAURICIO §4.2`](../PENDIENTES-MAURICIO.md)
> **Dueño:** Mauricio · **Plazo externo: lo aprueba Meta, y el reloj no empieza hasta que se manda.**
>
> **Qué NO hay que hacer aquí:** escribir código. El canal está completo y probado (53 tests).
> Todo lo de este runbook ocurre **fuera del repositorio**, en Meta Business Manager.
>
> **La trampa de esta tarea, y está a la vista desde el primer paso:** el paso lento no es la
> plantilla, es la **verificación del negocio**. Se empieza por ahí aunque lo demás no esté.

---

## 0 · Antes de empezar — lo que ya está resuelto y no debes rehacer

| | |
|---|---|
| Código del canal | **completo**, 53 tests en verde |
| Plantilla | **escrita en el repo**, en estado `PENDING` **a propósito** |
| Caída por pausa de Meta | **automática** — si Meta pausa la plantilla por calidad, el canal cae solo y queda en cuarentena persistida (`T-2.77.c`). No hay que hacer nada y no se martillea la plantilla pausada |
| Estado hoy del canal | **SIMULADO** — el orquestador escala al SMS mientras `status ≠ APPROVED` |

> **Y una regla que no se salta ni «para probar»:** no se pone `status: APPROVED` a mano. El canal
> se declara **SIMULADO** hasta que Meta apruebe de verdad. Poner `APPROVED` sin aprobación es
> exactamente la mentira que `T-2.75` erradicó — un canal que dice «entregado» sin haber entregado.

---

## 1 · Crear el WhatsApp Business Account

En **Meta Business Manager**, con el número que vayas a usar.

- **El número no puede estar ya dado de alta en WhatsApp normal** (ni en WhatsApp Business
  app). Si lo está, hay que borrarlo de ahí primero, y eso tarda.
- Conviene un número **dedicado** al sistema, no el personal ni el de ventas: el día que haya
  volumen, ese número recibe respuestas de gente asustada.

## 2 · Verificar el negocio — **empieza por aquí**

Meta pide documentación de la empresa. **Éste es el paso lento de todo el proceso**, y es
independiente de la plantilla: se puede lanzar hoy aunque no tengas decidido nada más.

Ten a mano: acta constitutiva o alta ante el SAT, comprobante de domicilio fiscal, y un sitio web
o correo con el dominio de la empresa.

> **Ojo, porque enlaza con otro pendiente:** el **dominio** aparece también en
> [`§2.9`](../PENDIENTES-MAURICIO.md) — sin dominio no hay DKIM/SPF y el correo transaccional
> sigue bloqueado. **Es el mismo trámite sirviendo a dos cosas.** Si vas a comprar dominio para
> Meta, cómpralo pensando también en SES.

## 3 · Mandar la plantilla a aprobación — **copiar, no reescribir**

**La plantilla ya está escrita.** Su texto se eligió para que Meta la clasifique como
**UTILITY** y no como marketing.

> **Por qué esto no es una preferencia de estilo:** si acabara en `MARKETING`, un destinatario que
> haya rechazado marketing **dejaría de recibir el aviso** (error 131050) — y nadie se enteraría
> **hasta el sismo siguiente**. Meta nombra explícitamente `public safety (severe weather, crisis
> response)` dentro de utility; el texto está redactado para caer ahí.

Cuerpo **literal** de `POST /<WABA_ID>/message_templates`:

```json
{
  "name": "takab_alerta_sismica_incidente",
  "language": "es_MX",
  "category": "UTILITY",
  "parameter_format": "positional",
  "message_send_ttl_seconds": 300,
  "allow_category_change": false,
  "components": [
    {
      "type": "BODY",
      "text": "TAKAB Ailert. ALERTA SÍSMICA: incidente activo en {{1}}. Severidad: {{2}}. Referencia del incidente: {{3}}. Protéjase y siga el protocolo de su inmueble. Consulte la consola de operación para el estado actualizado.",
      "example": {
        "body_text": [
          ["Torre Poniente", "critical", "1a2b3c4d"]
        ]
      }
    }
  ]
}
```

**Fuente de verdad:** `api/src/takab_api/notify/whatsapp_templates/incident_es_mx.json`. El bloque
`template` de ese fichero **es literalmente** el cuerpo de la petición: no hay traducción en medio,
y por eso lo que se revisa en un diff es lo mismo que revisa Meta.

> ### ⚠️ Cambiar una coma obliga a volver a pedir aprobación
> El candado es `approval.approved_digest`: un SHA-256 del bloque canónico. Si el texto del repo se
> mueve, **el digest se mueve y la plantilla deja de estar aprobada** — el canal vuelve a
> SIMULADO solo. Es a propósito: protege contra la deriva accidental, que es la que de verdad
> ocurre.
>
> **Digest del texto actual:**
> ```
> 0210ec27ae83ad8393f0e883cb23c0f6a1efdefa2c0a71c94064b29222651da6
> ```
> Es canónico (claves ordenadas), así que reindentar el fichero o reordenar claves **no**
> desaprueba una plantilla que no cambió. Solo el contenido cuenta.

**Dos parámetros del cuerpo que Meta fija AL CREAR y no al enviar:**

- `message_send_ttl_seconds: 300` — cinco minutos. Misma razón que el `ValidityPeriod` del SMS:
  **un aviso de sismo entregado horas después no es tarde, es desinformación.** El rango de utility
  admite hasta 12 h; se eligió el extremo corto a propósito.
- `allow_category_change: false` — si Meta quisiera reclasificarla a marketing, preferimos que
  **falle** a que se degrade en silencio al modo que pierde destinatarios.

## 4 · Cuando Meta apruebe

Guarda en **AWS Secrets Manager** los tres valores:

```
phone_number_id
access_token
app_secret
```

Y avísame: el código ya está, solo hay que cablearlo y sellar el fichero de la plantilla
(`status`, `approved_digest`, `meta_template_id`, `reviewed_at`).

> **`app_secret` aparece dos veces en la lista de pendientes y es el mismo secreto.**
> [`§2.1` punto 4](../PENDIENTES-MAURICIO.md) necesita `TAKAB_API_NOTIFY_WHATSAPP_APP_SECRET` y
> `TAKAB_API_NOTIFY_WHATSAPP_VERIFY_TOKEN` para los **webhooks de entrega**, más **abrir el 443 a
> los rangos de Meta** en el security group. Sin eso, el canal seguirá diciendo «el proveedor lo
> aceptó» y **nunca «llegó a una persona»**. Conviene hacer las dos cosas en la misma pasada.

---

## Estado

- [ ] 1 · WhatsApp Business Account creado
- [ ] 2 · Negocio verificado *(el lento — empezar primero)*
- [ ] 3 · Plantilla enviada a aprobación
- [ ] 4 · Aprobada por Meta · secretos en Secrets Manager
- [ ] 5 · Webhooks de entrega cableados (`§2.1` punto 4)
