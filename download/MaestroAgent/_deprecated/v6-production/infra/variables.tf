variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type        = string
  description = "staging or production"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be staging or production."
  }
}

variable "domain_name" {
  type        = string
  description = "e.g. app.maestro.com"
}

variable "db_instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
}

variable "ecr_uri" {
  type = string
}
