# Design: LocalStack Sandbox Adapter

## Architecture

The LocalStack adapter is a new implementation of the existing `SandboxPort` protocol. It manages a docker-compose stack (LocalStack + awscli sidecar) instead of a single Ubuntu container.

```
components/sandbox/
├── runtime/
│   ├── ports.py                    ← existing SandboxPort (unchanged)
│   ├── adapters/
│   │   ├── docker_adapter.py       ← existing (unchanged)
│   │   ├── mock.py                 ← existing (unchanged)
│   │   └── localstack_adapter.py   ← NEW
│   └── runtime.py                  ← add localstack to create_adapter()
└── ...

challenges/
├── idor_warehouse/                 ← existing Flask app
├── pentest-sandbox/                ← existing Dockerfile
├── localstack/                     ← NEW
│   ├── docker-compose.yml          ← LocalStack + awscli sidecar
│   └── deploy_challenges.sh        ← deploys all CFN templates
├── localstack-iam-privesc/         ← NEW
│   ├── template.yaml               ← vulnerable CFN
│   └── gt_entries.json             ← ground truth
└── localstack-ssrf-lambda/         ← NEW
    ├── template.yaml
    ├── handler.py                  ← vulnerable Lambda code
    └── gt_entries.json
```

## Key Design Decisions

### 1. Docker Compose, Not Raw Docker

LocalStack needs networking between the LocalStack container and the awscli sidecar. Docker Compose handles this naturally with a shared network. The adapter calls `docker compose up -d` and `docker compose down` instead of raw `docker run`.

### 2. AWS CLI Sidecar Pattern

Instead of installing AWS CLI inside LocalStack (which is an emulator, not a workspace), we run a separate "awscli" container on the same Docker network. `sandbox.execute()` runs commands in this sidecar. The sidecar has:
- AWS CLI v2 pre-installed
- `AWS_ENDPOINT_URL=http://localstack:4566` (all AWS commands auto-target LocalStack)
- `AWS_ACCESS_KEY_ID=test` / `AWS_SECRET_ACCESS_KEY=test` (LocalStack's default creds)
- Challenge templates mounted at `/challenges/`

### 3. ENFORCE_IAM=1

LocalStack's free tier doesn't enforce IAM by default — all API calls succeed regardless of permissions. Setting `ENFORCE_IAM=1` makes IAM policies actually enforced, so agents can discover real permission issues. This is critical for security testing realism.

### 4. Challenge Templates as CloudFormation

Each challenge is a CloudFormation template that deploys vulnerable AWS resources into LocalStack. This mirrors how real Amazon services are deployed (CDK → CloudFormation). The ground truth schema matches the existing `gt_entries.json` format from idor-warehouse.

## Docker Compose Configuration

```yaml
# challenges/localstack/docker-compose.yml
services:
  localstack:
    image: localstack/localstack:latest
    environment:
      - SERVICES=iam,lambda,s3,dynamodb,sqs,sns,apigateway,cloudformation,sts,ssm
      - ENFORCE_IAM=1
      - DEBUG=0
    ports:
      - "4566:4566"
    volumes:
      - localstack_data:/var/lib/localstack
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4566/_localstack/health"]
      interval: 5s
      timeout: 3s
      retries: 10

  awscli:
    image: amazon/aws-cli:latest
    entrypoint: ["sleep", "infinity"]
    environment:
      - AWS_ENDPOINT_URL=http://localstack:4566
      - AWS_DEFAULT_REGION=us-east-1
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test
    volumes:
      - ../localstack-iam-privesc:/challenges/iam-privesc
      - ../localstack-ssrf-lambda:/challenges/ssrf-lambda
    depends_on:
      localstack:
        condition: service_healthy

volumes:
  localstack_data:
```

## LocalStackAdapter Implementation

```python
class LocalStackAdapter:
    """SandboxPort implementation using LocalStack docker-compose."""

    async def provision(self, config: dict) -> str:
        # docker compose -f challenges/localstack/docker-compose.yml up -d
        # Wait for healthcheck
        # Return env_id = "localstack-{uuid}"

    async def execute(self, env_id: str, command: str, timeout: int = 300) -> dict:
        # docker compose exec awscli sh -c "{command}"
        # Returns {exit_code, stdout, stderr, duration_ms}

    async def terminate(self, env_id: str) -> None:
        # docker compose down -v

    async def get_status(self, env_id: str) -> dict:
        # curl http://localhost:4566/_localstack/health
```

## Challenge: IAM Privilege Escalation

```yaml
# challenges/localstack-iam-privesc/template.yaml
Resources:
  VulnerableLambdaRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: vulnerable-lambda-role
      AssumeRolePolicyDocument: ...
      Policies:
        - PolicyName: overly-permissive
          PolicyDocument:
            Statement:
              - Effect: Allow
                Action: ["iam:*", "s3:*", "lambda:*"]  # WAY too broad
                Resource: "*"

  PublicBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: public-data-bucket

  PublicBucketPolicy:
    Type: AWS::S3::BucketPolicy
    Properties:
      Bucket: !Ref PublicBucket
      PolicyDocument:
        Statement:
          - Effect: Allow
            Principal: "*"           # Public read — CWE-284
            Action: "s3:GetObject"
            Resource: !Sub "${PublicBucket.Arn}/*"

  NoAuthApi:
    Type: AWS::ApiGateway::RestApi
    Properties:
      Name: no-auth-api             # No authorizer — CWE-306
```

## E2E Test Flow

```
1. sandbox.provision(adapter="localstack")
   → docker compose up → LocalStack healthy

2. sandbox.execute("aws cloudformation deploy --template /challenges/iam-privesc/template.yaml --stack iam-privesc")
   → Deploys vulnerable resources

3. sandbox.execute("aws iam list-roles")
   → Discovers vulnerable-lambda-role with iam:*

4. sandbox.execute("aws s3api get-bucket-policy --bucket public-data-bucket")
   → Discovers public-read policy

5. sandbox.execute("aws sts assume-role --role-arn arn:aws:iam::000000000000:role/vulnerable-lambda-role")
   → Privilege escalation confirmed

6. graph_add_entity(finding-iam-privesc-001, Finding, {cwe: CWE-269, ...})
   → Finding persisted

7. metrics_record(metric_id="pentest-findings", value=3)
   → Metrics recorded

8. memory_memory_store("IAM privesc: vulnerable-lambda-role has iam:* ...")
   → Learning stored

9. sandbox.terminate()
   → docker compose down
```

## CWE Mapping for AWS Challenges

| Vulnerability | CWE | Challenge |
|--------------|-----|-----------|
| Overly permissive IAM role | CWE-269 (Improper Privilege Management) | iam-privesc |
| Public S3 bucket | CWE-284 (Improper Access Control) | iam-privesc |
| API Gateway without auth | CWE-306 (Missing Authentication) | iam-privesc |
| Unencrypted DynamoDB | CWE-311 (Missing Encryption) | iam-privesc |
| SSRF in Lambda | CWE-918 (Server-Side Request Forgery) | ssrf-lambda |
| Secret in SSM plaintext | CWE-312 (Cleartext Storage of Sensitive Info) | ssrf-lambda |

#[[file:components/sandbox/src/factory/sandbox/runtime/ports.py]] — SandboxPort protocol
#[[file:components/sandbox/src/factory/sandbox/runtime/adapters/docker_adapter.py]] — existing Docker adapter pattern
#[[file:challenges/idor_warehouse/gt_entries.json]] — GT entry schema reference
