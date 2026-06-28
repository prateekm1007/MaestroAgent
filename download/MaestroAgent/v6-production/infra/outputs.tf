output "vpc_id"           { value = module.vpc.vpc_id }
output "db_endpoint"      { value = aws_db_instance.main.address }
output "redis_endpoint"   { value = aws_elasticache_replication_group.main.primary_endpoint_address }
output "alb_dns"          { value = aws_lb.main.dns_name }
output "ecs_cluster_name" { value = aws_ecs_cluster.main.name }
output "ecr_uri"          { value = var.ecr_uri }
output "kms_key_arn"      { value = aws_kms_key.main.arn }
