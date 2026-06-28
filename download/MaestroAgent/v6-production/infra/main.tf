# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Maestro v6 — Terraform: Design Partner Infrastructure
# Single-tenant per design partner. Multi-tenant for GA (separate config).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    bucket         = "maestro-tfstate"
    key            = "design-partner/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "maestro-tflock"
  }
}

provider "aws" {
  region = var.aws_region
}

# ─── VPC ───
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name                 = "maestro-${var.environment}"
  cidr                 = "10.0.0.0/16"
  azs                  = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets      = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets       = ["10.0.101.0/24", "10.0.102.0/24"]
  enable_nat_gateway   = true
  enable_dns_hostnames = true
}

# ─── RDS PostgreSQL ───
resource "aws_db_subnet_group" "main" {
  name       = "maestro-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name        = "maestro-rds-${var.environment}"
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    security_groups = [aws_security_group.app.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main" {
  identifier             = "maestro-${var.environment}"
  engine                 = "postgres"
  engine_version         = "16.4"
  instance_class         = var.db_instance_class
  allocated_storage      = 100
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.main.arn
  username               = "maestro"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  backup_retention_period = 7
  multi_az               = var.environment == "production"
  deletion_protection    = var.environment == "production"
  skip_final_snapshot    = false
  final_snapshot_id      = "maestro-${var.environment}-final"
}

# ─── ElastiCache Redis ───
resource "aws_elasticache_subnet_group" "main" {
  name       = "maestro-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "redis" {
  name        = "maestro-redis-${var.environment}"
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "maestro-${var.environment}"
  description          = "Maestro Redis ${var.environment}"
  node_type            = var.redis_node_type
  num_cache_clusters   = 2
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token           = var.redis_auth_token
  automatic_failover_enabled = true
}

# ─── KMS Key ───
resource "aws_kms_key" "main" {
  description             = "Maestro ${var.environment} encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

# ─── S3 Bucket (audio + transcripts) ───
resource "aws_s3_bucket" "transcripts" {
  bucket = "maestro-${var.environment}-transcripts"
}

resource "aws_s3_bucket_versioning" "transcripts" {
  bucket = aws_s3_bucket.transcripts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "transcripts" {
  bucket = aws_s3_bucket.transcripts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "transcripts" {
  bucket = aws_s3_bucket.transcripts.id
  rule {
    id     = "transition-to-glacier"
    status = "Enabled"
    transition { days = 90 storage_class = "GLACIER" }
    expiration { days = 730 }
  }
}

# ─── ECS Cluster ───
resource "aws_ecs_cluster" "main" {
  name = "maestro-${var.environment}"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_security_group" "app" {
  name        = "maestro-app-${var.environment}"
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "maestro-${var.environment}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "2048"
  memory                   = "4096"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "api"
      image = "${var.ecr_uri}:latest"
      portMappings = [{ containerPort = 3000, protocol = "tcp" }]
      environment = [
        { name = "NODE_ENV", value = var.environment == "production" ? "production" : "staging" },
        { name = "DATABASE_URL", value = "postgresql://maestro:${var.db_password}@${aws_db_instance.main.address}:5432/maestro" },
        { name = "REDIS_URL", value = "rediss://:${var.redis_auth_token}@${aws_elasticache_replication_group.main.primary_endpoint_address}:6379" },
      ]
      secrets = [
        { name = "ENCRYPTION_KEY", valueFrom = "${aws_kms_key.main.arn}:encryption-key" },
        { name = "NEXTAUTH_SECRET", valueFrom = "${aws_kms_key.main.arn}:nextauth-secret" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
      healthCheck = {
        command = ["CMD-SHELL", "wget -qO- http://localhost:3000/api/health || exit 1"]
        interval = 30
        timeout  = 5
        retries  = 3
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "maestro-${var.environment}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.environment == "production" ? 3 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 3000
  }

  deployment_controller {
    type = "ECS"
  }

  lifecycle { ignore_changes = [desired_count] }
}

# ─── CloudWatch Logs ───
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/maestro-${var.environment}-api"
  retention_in_days = 30
}

# ─── CloudWatch Alarms ───
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "maestro-${var.environment}-api-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_sns_topic" "alerts" {
  name = "maestro-${var.environment}-alerts"
}

# ─── IAM ───
resource "aws_iam_role" "ecs_execution" {
  name = "maestro-${var.environment}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role" "ecs_task" {
  name = "maestro-${var.environment}-ecs-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

# ─── Load Balancer ───
resource "aws_lb" "main" {
  name               = "maestro-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  subnets            = module.vpc.public_subnets
  security_groups    = [aws_security_group.app.id]
}

resource "aws_lb_target_group" "api" {
  name        = "maestro-${var.environment}-api"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"
  health_check {
    path = "/api/health"
    matcher = "200"
    interval = 30
    timeout = 5
    healthy_threshold = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.main.arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_acm_certificate" "main" {
  domain_name       = var.domain_name
  validation_method = "DNS"
}
