#!/usr/bin/env bash
# Sube una nueva versión del backend a la EC2 ya creada y reinicia el servicio (vía SSM, sin SSH).
# Uso: bash infra/05_redeploy.sh
source "$(dirname "$0")/env.sh"

tar --exclude='__pycache__' -czf infra/.backend.tar.gz -C . backend
aws s3 cp infra/.backend.tar.gz "s3://${BUCKET}/code/backend.tar.gz"
INSTANCE_ID="$(aws ec2 describe-instances --filters Name=tag:Name,Values=airline-p2 Name=instance-state-name,Values=running \
               --query 'Reservations[0].Instances[0].InstanceId' --output text | tr -d '\r')"
CMD_ID="$(aws ssm send-command --instance-ids "$INSTANCE_ID" --document-name AWS-RunShellScript \
  --parameters "commands=[\"aws s3 cp s3://${BUCKET}/code/backend.tar.gz /opt/airline/backend.tar.gz\",\"rm -rf /opt/airline/backend\",\"tar -xzf /opt/airline/backend.tar.gz -C /opt/airline\",\"/opt/airline/venv/bin/pip install -q -r /opt/airline/backend/requirements.txt\",\"systemctl restart airline\"]" \
  --query Command.CommandId --output text | tr -d '\r')"
aws ssm wait command-executed --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" || true
aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --query '{status:Status,out:StandardOutputContent,err:StandardErrorContent}' --output json
