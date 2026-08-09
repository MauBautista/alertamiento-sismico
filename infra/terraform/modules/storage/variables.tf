variable "kms_key_arn" {
  type = string
}

variable "backfill_queue_arn" {
  type = string
}

variable "account_id" {
  type = string
}

# --- [T-2.72] PITR: la retencion es parte de la CADENA, no una preferencia ----
#
# Este modulo es el unico podador de la cadena de recuperacion (la instancia no
# tiene permiso de borrado sobre el bucket — ver `modules/database`). Por eso los
# numeros viven AQUI y bajan al modulo `database`, que los usa para programar el
# backup base y para negarse a arrancar el archivado si la desigualdad no se
# cumple. Al reves —el cron decidiendo su cadencia y el lifecycle adivinandola—
# la garantia se calcularia sobre un intervalo que no ocurre.

variable "db_dump_key_prefix" {
  description = <<-EOT
    Prefijo de clave del dump logico nocturno. NO es decorativo: es lo que
    separa la retencion del dump (60 d) de la de la cadena PITR. El cron que los
    escribe vive en `modules/database/user_data.sh.tpl` como
    `takab-$(date +%F).dump`; si uno de los dos cambia sin el otro, el dump deja
    de expirar (se acumula para siempre) o —peor— cae bajo una regla que no le
    corresponde.
  EOT
  type        = string
  default     = "takab-"
}

variable "pitr_prefix" {
  description = "Raiz de la cadena PITR dentro del bucket de respaldos. Barman escribe debajo `<prefijo><servidor>/wals/` y `<prefijo><servidor>/base/` (verificado contra la propia herramienta)."
  type        = string
  default     = "pitr/"

  validation {
    condition     = endswith(var.pitr_prefix, "/") && length(var.pitr_prefix) > 1
    error_message = "pitr_prefix debe terminar en '/' y no puede ser la raiz del bucket: un prefijo vacio volveria a mezclar la cadena PITR con el dump bajo la misma regla de expiracion."
  }
}

variable "pitr_server_name" {
  description = "Nombre de servidor Barman. Es un componente literal de la clave en S3, asi que la regla de lifecycle y el archivador tienen que decir el mismo."
  type        = string
  default     = "takab-dev-db"
}

variable "pitr_retention" {
  description = <<-EOT
    Retencion de la cadena PITR. `wal_days` aplica por igual a los WAL y a los
    backups base: son las dos mitades de la misma cadena y expirarlas a ritmos
    distintos la parte por en medio sin que nada falle hasta el dia del restore.
  EOT
  type = object({
    wal_days                  = number
    base_backup_interval_days = number
    chain_margin              = number
  })
  default = {
    wal_days                  = 14
    base_backup_interval_days = 7
    chain_margin              = 2
  }
}
