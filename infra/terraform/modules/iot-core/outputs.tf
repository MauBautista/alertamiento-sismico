output "thing_type_name" {
  value = aws_iot_thing_type.gateway.name
}

output "thing_group_name" {
  value = aws_iot_thing_group.gateways.name
}

output "fleet_policy_name" {
  value = aws_iot_policy.fleet.name
}

output "iot_endpoint" {
  value = data.aws_iot_endpoint.data_ats.endpoint_address
}

output "rule_errors_log_group_name" {
  value = aws_cloudwatch_log_group.rule_errors.name
}
