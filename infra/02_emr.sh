#!/usr/bin/env bash
# Lanza un cluster EMR efímero que corre curate.py como step y se apaga solo (R4, R10).
# Uso: bash infra/02_emr.sh sample   -> muestra pequeña, escribe en curated-sample/ (prueba barata)
#      bash infra/02_emr.sh full     -> dataset completo, escribe en curated/ (lo que lee Athena)
source "$(dirname "$0")/env.sh"
MODE="${1:?usar: sample | full}"
case "$MODE" in
  sample) RAW="s3://${BUCKET}/raw/sample/"; OUT="s3://${BUCKET}/curated-sample" ;;
  full)   RAW="s3://${BUCKET}/raw/full/";   OUT="s3://${BUCKET}/curated" ;;
  *) echo "modo inválido: $MODE"; exit 1 ;;
esac

aws s3 cp emr/curate.py "s3://${BUCKET}/code/curate.py"

cat > infra/.steps.json <<EOF
[{
  "Type": "Spark",
  "Name": "curate-${MODE}",
  "ActionOnFailure": "TERMINATE_CLUSTER",
  "Args": ["--deploy-mode", "client",
           "--conf", "spark.executor.memory=2g",
           "--conf", "spark.executor.cores=1",
           "--conf", "spark.driver.memory=2g",
           "--conf", "spark.sql.shuffle.partitions=48",
           "s3://${BUCKET}/code/curate.py",
           "--raw", "${RAW}",
           "--curated", "${OUT}/reservations_curated/",
           "--metrics", "${OUT}/route_month_metrics/"]
}]
EOF

# 1 master + 1 core, ambos m4.large (el único tipo permitido). Se probó primero con UN solo nodo
# y no funcionó dos veces:
#   1) modo cluster con la memoria por defecto de EMR: driver (~2.4 GB) + executor (~5 GB) no caben
#      en los ~6 GB de YARN -> "Initial job has not accepted any resources" para siempre.
#   2) modo client con executors de 2 GB: el master solo, con 8 GB, tiene que alojar además HDFS,
#      YARN, el driver y los agentes de EMR; quedó saturado (ni siquiera subía sus logs a S3).
# Con un nodo core aparte, el master solo coordina y el core ofrece ~6 GB de YARN a 2 executors de
# 2 GB. Cuesta 8 horas normalizadas por corrida (tope R10: 150).
# --auto-terminate: el cluster se destruye al terminar el último step, falle o no. Así R10 no
# depende de que alguien se acuerde de apagarlo.
CLUSTER_ID="$(aws emr create-cluster \
  --name "airline-curate-${MODE}" \
  --release-label emr-6.15.0 \
  --applications Name=Spark \
  --instance-groups InstanceGroupType=MASTER,InstanceCount=1,InstanceType=m4.large \
                    InstanceGroupType=CORE,InstanceCount=1,InstanceType=m4.large \
  --service-role EMR_DefaultRole \
  --ec2-attributes InstanceProfile=EMR_EC2_DefaultRole \
  --log-uri "s3://${BUCKET}/emr-logs/" \
  --steps file://infra/.steps.json \
  --auto-terminate \
  --query ClusterId --output text | tr -d '\r')"
echo "Cluster: ${CLUSTER_ID} (esperando a que termine; ~10-15 min)"

aws emr wait cluster-terminated --cluster-id "$CLUSTER_ID" || true
aws emr list-steps --cluster-id "$CLUSTER_ID" \
  --query 'Steps[].{step:Name,state:Status.State,start:Status.Timeline.StartDateTime,end:Status.Timeline.EndDateTime}' --output table
aws emr describe-cluster --cluster-id "$CLUSTER_ID" \
  --query 'Cluster.{state:Status.State,reason:Status.StateChangeReason.Message,normalizedHours:NormalizedInstanceHours}' --output table
aws s3 ls "${OUT}/" --recursive --summarize --human-readable | tail -3
