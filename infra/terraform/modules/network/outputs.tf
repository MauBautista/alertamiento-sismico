output "vpc_id" {
  value = aws_vpc.this.id
}

output "subnet_ids" {
  value = [for s in aws_subnet.public : s.id]
}

output "sg_workers_id" {
  value = aws_security_group.workers.id
}

output "sg_db_id" {
  value = aws_security_group.db.id
}

output "route_table_id" {
  value = aws_route_table.public.id
}
