# Variables comunes. Uso: source infra/env.sh  (desde la raíz del repo, en Git Bash)
# Las credenciales NO van aquí: el CLI las lee de ~/.aws/credentials (copiadas del Learner Lab).
set -euo pipefail
export MSYS_NO_PATHCONV=1            # Git Bash: no convertir argumentos que empiezan con '/'

if ! command -v aws >/dev/null 2>&1; then
  aws() { "/c/Program Files/Amazon/AWSCLIV2/aws.exe" "$@"; }
fi

export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_PAGER=""
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text | tr -d '\r')"
export ACCOUNT_ID
export BUCKET="airline-p2-${ACCOUNT_ID}"
export ATHENA_DB="airline_analytics"
export ATHENA_OUTPUT="s3://${BUCKET}/athena-results/"
export SEED=190
