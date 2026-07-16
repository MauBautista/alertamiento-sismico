output "apns_application_arn" {
  value = local.apns_enabled ? aws_sns_platform_application.apns[0].arn : ""
}

output "fcm_application_arn" {
  value = local.fcm_enabled ? aws_sns_platform_application.fcm[0].arn : ""
}

# Para el env de la API: TAKAB_API_PUSH_APNS_APPLICATION_ARN / _FCM_.
output "push_enabled" {
  value = local.push_enabled
}
