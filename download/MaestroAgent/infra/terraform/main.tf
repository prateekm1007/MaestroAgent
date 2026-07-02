# Maestro — Production AWS Infrastructure (Terraform)
# Creates: VPC, RDS PostgreSQL, ElastiCache Redis, ECS Fargate (API + Worker),
# ALB, CloudWatch, S3, KMS, Secrets Manager, Route53, Auto-scaling

terraform {
  required_version = ">= 1.5"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
  backend "s3" { bucket = "maestro-tfstate" key = "production/terraform.tfstate" region = "us-east-1" }
}

variable "aws_region" { default = "us-east-1" }
variable "environment" { default = "production" }
variable "domain_name" { default = "maestro.app" }
variable "db_password" { sensitive = true }
variable "jwt_secret" { sensitive = true }
variable "encryption_key" { sensitive = true }

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  name = "maestro-${var.environment}" cidr = "10.0.0.0/16"
  azs = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets = ["10.0.101.0/24", "10.0.102.0/24"]
  enable_nat_gateway = true single_nat_gateway = true
  tags = { Environment = var.environment }
}

resource "aws_kms_key" "maestro" {
  description = "Maestro ${var.environment} encryption key"
  deletion_window_in_days = 30 enable_key_rotation = true
}

resource "aws_db_subnet_group" "maestro" { name = "maestro-${var.environment}" subnet_ids = module.vpc.private_subnets }

resource "aws_db_instance" "maestro" {
  identifier = "maestro-${var.environment}"
  engine = "postgres" engine_version = "16.2" instance_class = "db.r6g.large"
  allocated_storage = 100 max_allocated_storage = 500
  storage_encrypted = true kms_key_id = aws_kms_key.maestro.arn
  db_name = "maestro" username = "maestro" password = var.db_password
  db_subnet_group_name = aws_db_subnet_group.maestro.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az = true backup_retention_period = 7 deletion_protection = true
  copy_tags_to_snapshot = true
}

resource "aws_elasticache_subnet_group" "maestro" { name = "maestro-${var.environment}" subnet_ids = module.vpc.private_subnets }

resource "aws_elasticache_replication_group" "maestro" {
  replication_group_id = "maestro-${var.environment}"
  description = "Maestro Redis" node_type = "cache.r6g.large" num_cache_clusters = 2
  subnet_group_name = aws_elasticache_subnet_group.maestro.name
  security_group_ids = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true transit_encryption_enabled = true
  automatic_failover_enabled = true
}

resource "aws_s3_bucket" "artifacts" { bucket = "maestro-${var.environment}-artifacts" }
resource "aws_s3_bucket" "backups" { bucket = "maestro-${var.environment}-backups" }

resource "aws_ecs_cluster" "maestro" {
  name = "maestro-${var.environment}"
  setting { name = "containerInsights" value = "enabled" }
}

resource "aws_cloudwatch_log_group" "api" { name = "/maestro/${var.environment}/api" retention_in_days = 30 }
resource "aws_cloudwatch_log_group" "worker" { name = "/maestro/${var.environment}/worker" retention_in_days = 30 }

resource "aws_ecr_repository" "api" { name = "maestro/api" }
resource "aws_ecr_repository" "worker" { name = "maestro/worker" }

resource "aws_security_group" "alb" {
  name = "maestro-alb" vpc_id = module.vpc.vpc_id
  ingress { port = 443 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] }
  ingress { port = 80 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] }
  egress { port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_security_group" "ecs" {
  name = "maestro-ecs" vpc_id = module.vpc.vpc_id
  ingress { port = 1420 protocol = "tcp" security_groups = [aws_security_group.alb.id] }
  egress { port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_security_group" "rds" {
  name = "maestro-rds" vpc_id = module.vpc.vpc_id
  ingress { port = 5432 protocol = "tcp" security_groups = [aws_security_group.ecs.id] }
  egress { port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_security_group" "redis" {
  name = "maestro-redis" vpc_id = module.vpc.vpc_id
  ingress { port = 6379 protocol = "tcp" security_groups = [aws_security_group.ecs.id] }
  egress { port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_lb" "maestro" {
  name = "maestro-${var.environment}" internal = false
  load_balancer_type = "application" security_groups = [aws_security_group.alb.id]
  subnets = module.vpc.public_subnets
}

resource "aws_lb_target_group" "api" {
  name = "maestro-api" port = 1420 protocol = "HTTP" vpc_id = module.vpc.vpc_id
  health_check { path = "/api/health" matcher = "200" interval = 30 }
  deregistration_delay = 30
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.maestro.arn port = 443 protocol = "HTTPS"
  ssl_policy = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn = aws_acm_certificate.maestro.arn
  default_action { type = "forward" target_group_arn = aws_lb_target_group.api.arn }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.maestro.arn port = 80 protocol = "HTTP"
  default_action { type = "redirect" redirect { port = 443 protocol = "HTTPS" status_code = "HTTP_301" } }
}

resource "aws_acm_certificate" "maestro" { domain_name = var.domain_name validation_method = "DNS" }

resource "aws_iam_role" "ecs_execution" {
  name = "maestro-ecs-execution"
  assume_role_policy = jsonencode({ Version = "2012-10-17" Statement = [{ Action = "sts:AssumeRole" Principal = { Service = "ecs-tasks.amazonaws.com" } Effect = "Allow" }] })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role = aws_iam_role.ecs_execution.name policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_ecs_task_definition" "api" {
  family = "maestro-api" network_mode = "awsvpc" requires_compatibilities = ["FARGATE"]
  cpu = "1024" memory = "2048"
  execution_role_arn = aws_iam_role.ecs_execution.arn
  container_definitions = jsonencode([{ name = "api" image = "${aws_ecr_repository.api.repository_url}:latest" cpu = 1024 memory = 2048 portMappings = [{ containerPort = 1420 }] essential = true logConfiguration = { logDriver = "awslogs" options = { "awslogs-group" = aws_cloudwatch_log_group.api.name "awslogs-region" = var.aws_region "awslogs-stream-prefix" = "api" } } }])
}

resource "aws_ecs_service" "api" {
  name = "maestro-api" cluster = aws_ecs_cluster.maestro.id
  task_definition = aws_ecs_task_definition.api.arn desired_count = 2 launch_type = "FARGATE"
  network_configuration { subnets = module.vpc.private_subnets security_groups = [aws_security_group.ecs.id] assign_public_ip = false }
  load_balancer { target_group_arn = aws_lb_target_group.api.arn container_name = "api" container_port = 1420 }
  deployment_configuration { maximum_percent = 200 minimum_healthy_percent = 100 deployment_circuit_breaker { enable = true rollback = true } }
}

resource "aws_appautoscaling_target" "api" {
  max_capacity = 10 min_capacity = 2
  resource_id = "service/${aws_ecs_cluster.maestro.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount" service_namespace = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name = "maestro-api-cpu" policy_type = "TargetTrackingScaling"
  resource_id = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace = aws_appautoscaling_target.api.service_namespace
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification { predefined_metric_type = "ECSServiceAverageCPUUtilization" }
    target_value = 70 scale_in_cooldown = 300 scale_out_cooldown = 60
  }
}

resource "aws_ecs_task_definition" "worker" {
  family = "maestro-worker" network_mode = "awsvpc" requires_compatibilities = ["FARGATE"]
  cpu = "512" memory = "1024" execution_role_arn = aws_iam_role.ecs_execution.arn
  container_definitions = jsonencode([{ name = "worker" image = "${aws_ecr_repository.worker.repository_url}:latest" cpu = 512 memory = 1024 essential = true logConfiguration = { logDriver = "awslogs" options = { "awslogs-group" = aws_cloudwatch_log_group.worker.name "awslogs-region" = var.aws_region "awslogs-stream-prefix" = "worker" } } }])
}

resource "aws_ecs_service" "worker" {
  name = "maestro-worker" cluster = aws_ecs_cluster.maestro.id
  task_definition = aws_ecs_task_definition.worker.arn desired_count = 1 launch_type = "FARGATE"
  network_configuration { subnets = module.vpc.private_subnets security_groups = [aws_security_group.ecs.id] assign_public_ip = false }
}

resource "aws_appautoscaling_target" "worker" {
  max_capacity = 5 min_capacity = 1
  resource_id = "service/${aws_ecs_cluster.maestro.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount" service_namespace = "ecs"
}

resource "aws_route53_record" "maestro" {
  zone_id = data.aws_route53_zone.maestro.zone_id name = var.domain_name type = "A"
  alias { name = aws_lb.maestro.dns_name zone_id = aws_lb.maestro.zone_id evaluate_target_health = true }
}

data "aws_route53_zone" "maestro" { name = var.domain_name private_zone = false }

output "alb_dns" { value = aws_lb.maestro.dns_name }
output "db_endpoint" { value = aws_db_instance.maestro.endpoint }
output "redis_endpoint" { value = aws_elasticache_replication_group.maestro.primary_endpoint_address }
