#!/usr/bin/env bash
set -euo pipefail

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Maestro v6 — Deploy Script
# Usage: ./scripts/deploy.sh staging|production
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ENVIRONMENT="${1:-}"
if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
  echo "Usage: $0 staging|production"
  exit 1
fi

echo "━━━ Maestro v6 deploy: $ENVIRONMENT ━━━"

# ─── Pre-flight checks ───
echo "▶ Pre-flight checks..."

if [[ -z "${AWS_REGION:-}" ]]; then echo "✗ AWS_REGION not set"; exit 1; fi
if [[ -z "${ECR_URI:-}" ]]; then echo "✗ ECR_URI not set"; exit 1; fi
if [[ -z "${TF_VAR_db_password:-}" ]]; then echo "✗ TF_VAR_db_password not set"; exit 1; fi
if [[ -z "${TF_VAR_redis_auth_token:-}" ]]; then echo "✗ TF_VAR_redis_auth_token not set"; exit 1; fi
if [[ -z "${TF_VAR_domain_name:-}" ]]; then echo "✗ TF_VAR_domain_name not set"; exit 1; fi

echo "✓ All env vars present"

# ─── Build & push Docker image ───
GIT_SHA=$(git rev-parse --short HEAD)
echo "▶ Building Docker image (sha: $GIT_SHA)..."

docker build -t maestro-v6:$GIT_SHA .
docker tag maestro-v6:$GIT_SHA $ECR_URI:$GIT_SHA
docker tag maestro-v6:$GIT_SHA $ECR_URI:latest

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI
docker push $ECR_URI:$GIT_SHA
docker push $ECR_URI:latest

echo "✓ Image pushed"

# ─── Terraform apply ───
echo "▶ Terraform apply ($ENVIRONMENT)..."

cd infra
terraform init -backend-config="key=$ENVIRONMENT/terraform.tfstate"
terraform apply -auto-approve \
  -var="environment=$ENVIRONMENT" \
  -var="ecr_uri=$ECR_URI"

ALB_DNS=$(terraform output -raw alb_dns)
echo "✓ Terraform applied — ALB: $ALB_DNS"

cd ..

# ─── Run database migrations ───
echo "▶ Running database migrations..."

aws ecs run-task \
  --cluster maestro-$ENVIRONMENT \
  --task-definition maestro-$ENVIRONMENT-migrate \
  --count 1 \
  --started-by "deploy-script-$GIT_SHA"

echo "✓ Migrations complete"

# ─── Force new deployment ───
echo "▶ Forcing new ECS deployment..."

aws ecs update-service \
  --cluster maestro-$ENVIRONMENT \
  --service maestro-$ENVIRONMENT-api \
  --force-new-deployment

echo "▶ Waiting for deployment to stabilize..."

aws ecs wait services-stable \
  --cluster maestro-$ENVIRONMENT \
  --services maestro-$ENVIRONMENT-api

echo "✓ Deployment stable"

# ─── Health check ───
echo "▶ Health check..."

PROTOCOL="https"
if [[ "$ENVIRONMENT" == "staging" ]]; then
  PROTOCOL="http"
fi

for i in {1..10}; do
  if curl -fsS "$PROTOCOL://$ALB_DNS/api/health" | jq -e '.status == "ok"'; then
    echo "✓ Health check passed"
    break
  fi
  echo "  Attempt $i failed, retrying in 5s..."
  sleep 5
  if [[ $i -eq 10 ]]; then
    echo "✗ Health check failed after 10 attempts"
    exit 1
  fi
done

# ─── Run smoke tests ───
echo "▶ Running smoke tests..."

SMOKE_URL="$PROTOCOL://$ALB_DNS" npx playwright test --project=chromium --grep="@smoke"

echo "✓ Smoke tests passed"

# ─── Done ───
echo ""
echo "━━━ Deploy complete ━━━"
echo "Environment: $ENVIRONMENT"
echo "URL: $PROTOCOL://$ALB_DNS"
echo "SHA: $GIT_SHA"
echo "━━━━━━━━━━━━━━━━━━━━━━━"
