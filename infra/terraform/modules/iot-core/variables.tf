variable "account_id" {
  type = string
}

variable "region" {
  type = string
}

variable "events_queue" {
  type = object({
    url = string
    arn = string
  })
}

variable "telemetry_queue" {
  type = object({
    url = string
    arn = string
  })
}
