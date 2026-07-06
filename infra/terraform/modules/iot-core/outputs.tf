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
