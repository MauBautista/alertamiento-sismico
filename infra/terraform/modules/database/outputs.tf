output "instance_id" {
  value = aws_instance.db.id
}

output "private_ip" {
  value = aws_instance.db.private_ip
}

output "public_ip" {
  value = aws_instance.db.public_ip
}

output "secret_arns" {
  value = { for k, s in aws_secretsmanager_secret.db : k => s.arn }
}

output "db_endpoint" {
  value = "${aws_instance.db.private_ip}:5432"
}

# ENI primaria: el SG web (modulo `serve`) se adjunta aqui, no a la instancia, para
# poder desconectar el acceso publico sin recrear la maquina.
output "primary_network_interface_id" {
  value = aws_instance.db.primary_network_interface_id
}

# [T-2.04] Rol IAM de la instancia (la API/worker corre aquí en dev): el módulo
# `push` le adjunta los permisos de SNS platform endpoints.
output "instance_role_name" {
  value = aws_iam_role.db.name
}

# [T-2.72] La edad maxima tolerada del archivado viaja de AQUI a
# `modules/observability`, donde se convierte en el umbral de la alarma y, por
# tanto, en el termino dominante del RPO. Es una sola cifra con un solo dueño: si
# el entorno cablease un literal en la alarma, el `archive_timeout` de esta
# instancia se estaria validando contra un numero que no es el que vigila nadie.
output "wal_archive_max_age_s" {
  value = var.wal_archive_max_age_s
}

# [T-2.72.b] El umbral de la alarma del BACKUP BASE, derivado de las MISMAS
# variables que gobiernan la retencion.
#
# No es un numero de politica: es un termino de la desigualdad que mantiene viva
# la cadena (`wal_retention_days >= base_backup_interval_days * chain_margin`,
# validada en `variables.tf`). Se calcula aqui —y no en `modules/observability`—
# porque este es el unico modulo donde estan las dos cifras y donde se programa el
# cron que produce esos backups. Un literal en la alarma se desincroniza el dia
# que cambie la politica de retencion y la vigilancia pasaria a describir una
# cadena distinta de la que el lifecycle de S3 poda.
#
# LO QUE ESTE UMBRAL NO ES, y conviene tenerlo escrito: NO es un aviso temprano.
# Cuando la edad del ancla supera `intervalo * margen`, ya han fallado `margen`
# backups base SEGUIDOS, y con los valores por defecto ese producto (7 x 2 = 14
# dias) es EXACTAMENTE `wal_retention_days` — o sea que el correo llega justo
# cuando la ventana de recuperacion se esta cerrando, no antes. Es lo que pide la
# ficha (T-2.72.b) y es lo unico que se puede derivar de las variables de
# retencion; un aviso temprano de verdad seria una segunda alarma a `intervalo`
# dias, que caza el PRIMER backup base fallido. Queda fichado, no supuesto.
output "base_backup_max_age_s" {
  description = "Edad maxima tolerada del ultimo backup base, en segundos: `base_backup_interval_days * chain_margin` dias."
  value       = var.pitr.base_backup_interval_days * var.pitr.chain_margin * 86400
}

# [T-2.141] Y EL AVISO, que es lo que el output de arriba dejo fichado.
#
# El mismo intervalo SIN el margen. La aritmetica no es una eleccion de estilo:
# es la definicion del hecho que hay que cazar. El cron corre en `*/N` del dia del
# mes, asi que el hueco entre dos backups base nunca pasa de `N` dias; el primer
# instante en que la edad del ancla SUPERA `N` dias es, exactamente, el primer
# `barman-cloud-backup` que no se completo. Ni antes (seria ruido del propio
# ciclo) ni despues (ya habria fallado mas de uno).
#
# LAS DOS DERIVAN DE LAS MISMAS VARIABLES Y NINGUNA REPITE UN NUMERO: aquella es
# `intervalo * margen`, esta es `intervalo`. El cociente entre las dos es
# `chain_margin`, y esa relacion es la que hace que el aviso llegue con
# `intervalo * (margen - 1)` dias de ventana por delante — con los valores por
# defecto, 7 dias para relanzar el backup a mano antes de que se cierre.
#
# Y por eso son DOS ALARMAS Y NO UNA: no dicen lo mismo ni piden lo mismo. Esta
# dice "fallo UNO, relanzalo"; la otra dice "fallaron `margen`, la ventana ya se
# cerro". Una sola alarma solo puede decir una de las dos cosas, y `T-2.72.b`
# eligio la segunda porque es la unica que se puede derivar del par completo.
# [T-2.154] El intervalo MAS UNA GRACIA, y la gracia no es para que deje de sonar.
#
# El umbral era el intervalo EXACTO, y eso garantizaba un falso positivo por
# ciclo: la edad cruza el umbral en el instante en que arranca el backup nuevo, y
# no baja hasta que la metrica lo refleja. Medido el 2026-08-22 sobre los objetos
# de S3:
#
#   backup 20260815: 04:00:02 -> 04:04:44  (4m42s, 276 MB)
#   backup 20260822: 04:00:02 -> 04:05:41  (5m39s, 329 MB)  <- +19% en una semana
#
# Con el scan corriendo YA al terminar el backup, la ventana real es esa duracion:
# ~6 min hoy. La gracia de 3600 s la cubre con 10x de holgura y deja sitio al
# crecimiento, y aun asi es el 0,6% del intervalo: la alarma sigue avisando el
# mismo dia que falle un backup.
#
# NO es "subirlo hasta que calle". Su hermana `base_backup_max_age_s` esta en
# `intervalo x margen` (14 dias) y sigue siendo la ultima linea; si esta se
# relajara hasta parecerse a aquella, quedarian dos alarmas para el caso tardio y
# NINGUNA para el temprano.
output "base_backup_warn_age_s" {
  description = "Edad del ultimo backup base a partir de la cual AVISAR, en segundos: `base_backup_interval_days` dias MAS `base_backup_grace_s`. La gracia cubre la duracion del backup, no relaja la vigilancia. Su hermana `base_backup_max_age_s` es la ultima linea."
  value       = var.pitr.base_backup_interval_days * 86400 + var.pitr.base_backup_grace_s
}

# La configuracion PITR tal y como quedo, para que el runbook pueda CITAR lo que
# produce la maquina en vez de lo que tecleo un humano.
output "pitr" {
  value = {
    prefix                    = var.pitr.prefix
    server_name               = var.pitr.server_name
    archive_timeout_s         = var.wal_archive_timeout_s
    max_archive_age_s         = var.wal_archive_max_age_s
    wal_retention_days        = var.pitr.wal_retention_days
    base_backup_interval_days = var.pitr.base_backup_interval_days
    chain_margin              = var.pitr.chain_margin
    ssm_document              = aws_ssm_document.pitr.name
  }
}

# [T-2.81.a] El umbral de la alarma de la retencion de PII, DERIVADO de la
# cadencia del cron que vive en este modulo (diaria) por el margen declarado. Un
# literal en `modules/observability` se desincronizaria el dia que la cadencia
# cambie, y la alarma pasaria a vigilar una periodicidad que no ocurre.
output "pii_retention_max_age_s" {
  description = "Edad maxima tolerada de la ultima corrida CORRECTA de retencion de PII, en segundos: cadencia diaria x `pii_retention_chain_margin`."
  value       = var.pii_retention_chain_margin * 86400
}

# Lo que produce la maquina, para que el runbook pueda CITARLO en vez de repetir
# lo que alguien tecleo.
output "pii_retention" {
  value = {
    ssm_document   = aws_ssm_document.prune_pii.name
    schedule_utc   = "06:00"
    metric_name    = local.pii_retention_metric_name
    max_age_s      = var.pii_retention_chain_margin * 86400
    windows_days   = var.pii_retention_windows_days
    reglas_activas = length(var.pii_retention_windows_days)
  }
}
