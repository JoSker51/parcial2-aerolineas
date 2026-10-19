#!/usr/bin/env bash
# Crea la única EC2 del sistema (t3.small): API + frontend + PostgreSQL.
# Uso: bash infra/04_ec2.sh
source "$(dirname "$0")/env.sh"

# Empaqueta el backend (incluye static/ y sql/) y lo deja en S3 para que la EC2 lo descargue.
tar --exclude='__pycache__' -czf infra/.backend.tar.gz -C . backend
aws s3 cp infra/.backend.tar.gz "s3://${BUCKET}/code/backend.tar.gz"

VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text | tr -d '\r')"
SG_ID="$(aws ec2 describe-security-groups --filters Name=group-name,Values=airline-p2-web Name=vpc-id,Values="$VPC_ID" \
          --query 'SecurityGroups[0].GroupId' --output text | tr -d '\r')"
if [ "$SG_ID" = "None" ]; then
  SG_ID="$(aws ec2 create-security-group --group-name airline-p2-web --vpc-id "$VPC_ID" \
            --description "Airline parcial 2: API+frontend en 8000" --query GroupId --output text | tr -d '\r')"
  # 8000 abierto: el profesor corre el harness desde su red. 5432 NO se abre: la base es local.
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 8000 --cidr 0.0.0.0/0
  MY_IP="$(curl -s https://checkip.amazonaws.com | tr -d '\r\n')"
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "${MY_IP}/32"
fi

AMI_ID="$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
          --query Parameter.Value --output text | tr -d '\r')"
sed -e "s#__BUCKET__#${BUCKET}#g" -e "s#__ATHENA_OUTPUT__#${ATHENA_OUTPUT}#g" infra/ec2-userdata.sh > infra/.userdata.sh

# LabInstanceProfile -> LabRole: la API llama a Athena/S3 sin claves guardadas en la máquina.
INSTANCE_ID="$(aws ec2 run-instances \
  --image-id "$AMI_ID" --instance-type t3.small \
  --key-name vockey \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name=LabInstanceProfile \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":8,"VolumeType":"gp3"}}]' \
  --user-data file://infra/.userdata.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=airline-p2}]' \
  --query 'Instances[0].InstanceId' --output text | tr -d '\r')"
echo "Instancia: $INSTANCE_ID"
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
      --query 'Reservations[0].Instances[0].PublicIpAddress' --output text | tr -d '\r')"
echo "IP pública: $IP  -> http://${IP}:8000  (el user-data tarda ~3 min en dejar la API arriba)"
