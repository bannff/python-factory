"""Sandbox resource creation and validation commands for LocalStack.

Per-resource-type AWS CLI commands used by sandbox setup agents.
Labels match Veritas PROP_MAP exactly.
"""
from __future__ import annotations

_AWS = (
    "AWS_DEFAULT_REGION=us-east-1 "
    "AWS_ACCESS_KEY_ID=test "
    "AWS_SECRET_ACCESS_KEY=test "
    "aws --endpoint-url=http://localhost:4566"
)

# ── Resource creation commands (keyed by Veritas label) ──────────────

SANDBOX_RESOURCE_COMMANDS: dict[str, str] = {
    "DynamoDB": (
        f"{_AWS} dynamodb create-table --table-name <name> "
        "--attribute-definitions AttributeName=pk,AttributeType=S "
        "--key-schema AttributeName=pk,KeyType=HASH "
        "--billing-mode PAY_PER_REQUEST"
    ),
    "SQS": (
        f"{_AWS} sqs create-queue --queue-name <name>"
    ),
    "S3": (
        f"{_AWS} s3 mb s3://<name>"
    ),
    "IamRole": (
        f"{_AWS} iam create-role --role-name <name> "
        "--assume-role-policy-document "
        "'{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":"
        "\"Allow\",\"Principal\":{\"Service\":"
        "\"lambda.amazonaws.com\"},\"Action\":"
        "\"sts:AssumeRole\"}]}'"
    ),
    "Lambda": (
        f"{_AWS} lambda create-function --function-name <name> "
        "--runtime python3.12 --handler index.handler "
        "--role arn:aws:iam::000000000000:role/lambda-role "
        "--zip-file fileb:///dev/null"
    ),
    "SNS": (
        f"{_AWS} sns create-topic --name <name>"
    ),
    "KMS": (
        f"{_AWS} kms create-key"
    ),
    "Secret": (
        f"{_AWS} secretsmanager create-secret "
        "--name <name> --secret-string '{}'"
    ),
    "ECSCluster": (
        f"{_AWS} ecs create-cluster --cluster-name <name>"
    ),
    "ApiGateway": (
        f"{_AWS} apigateway create-rest-api --name <name>"
    ),
    "SSMParameter": (
        f"{_AWS} ssm put-parameter --name <name> "
        "--value 'placeholder' --type String"
    ),
}

# ── Validation / list commands (keyed by Veritas label) ──────────────

SANDBOX_VALIDATION_COMMANDS: dict[str, str] = {
    "DynamoDB": f"{_AWS} dynamodb list-tables",
    "SQS": f"{_AWS} sqs list-queues",
    "S3": f"{_AWS} s3 ls",
    "IamRole": f"{_AWS} iam list-roles",
    "Lambda": f"{_AWS} lambda list-functions",
    "SNS": f"{_AWS} sns list-topics",
    "KMS": f"{_AWS} kms list-keys",
    "Secret": f"{_AWS} secretsmanager list-secrets",
    "ECSCluster": f"{_AWS} ecs list-clusters",
    "ApiGateway": f"{_AWS} apigateway get-rest-apis",
    "SSMParameter": f"{_AWS} ssm describe-parameters",
}
