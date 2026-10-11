# Milestone 5 — student-budget AWS cost estimate (estimate only)

**Status:** Approved for planning only. **No AWS resources have been provisioned** and no deployment/IaC code is included in this document.

| Field | Value |
| --- | --- |
| **Region** | US East (N. Virginia) — `us-east-1` |
| **Prices checked** | **11 October 2026** (public list prices on AWS pricing pages linked below) |
| **Billing model** | On-Demand, single-AZ, Linux/x86 Fargate, 730 hours/month |

This estimate matches [Milestone 5 in project-context.md](./project-context.md): ECS Fargate (API + workers), RDS PostgreSQL, ElastiCache Redis, S3, CloudWatch, cheap static frontend hosting, **private** RDS/Redis, least-privilege IAM, IaC when you implement, and a teardown procedure.

---

## 1. Proposed architecture (student budget)

```text
Internet
   │
   ├─► CloudFront (Free plan) ──► S3 bucket (static React build, OAC)
   │
   └─► Route 53 (optional; DNS included on CloudFront Free plan)
           │
           ▼
       Application Load Balancer (public subnets, HTTPS)
           │
           ▼
       ECS Fargate — API service (private subnets, no public IP)
           │
           ├──► RDS PostgreSQL 16 (private subnet, no public access)
           ├──► ElastiCache Redis 7 (private subnet)
           ├──► S3 — uploads + report exports (VPC gateway endpoint; no NAT for S3)
           └──► Secrets Manager — DB URL, JWT/CSRF secrets

       ECS Fargate — Celery worker + beat (private subnets)
           │
           ├──► same RDS / Redis / S3 as API
           └──► pulls images via NAT Gateway (or ECR interface endpoints)

       CloudWatch Logs + Container Insights (light) + Prometheus metrics already in-app → `/metrics` scraped optionally

       NAT Gateway (single AZ) — outbound from private subnets (PyPI/nflverse, ECR, etc.)
```

**Cost-conscious choices**

- **One NAT Gateway** (not one per AZ). Acceptable for a portfolio/student stack; document that AZ loss affects outbound pulls until recovery.
- **S3 gateway endpoint** (no hourly charge) so upload/download traffic to S3 does not traverse the NAT.
- **Frontend on CloudFront Free plan** ($0/month flat; includes DNS, TLS, 1M requests, 100 GB data transfer per distribution per [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/)). Alternative: Cloudflare Pages free tier (non-AWS) if you want zero AWS edge cost.
- **Single-AZ RDS and single Redis node** — no Multi-AZ (roughly doubles database/cache cost).
- **IaC (later):** Terraform or AWS CDK in a dedicated `infra/` directory; one state bucket + lock table; `terraform destroy` / `cdk destroy` as part of teardown.

**Least-privilege IAM (sketch)**

| Role | Purpose | Grants (examples) |
| --- | --- | --- |
| `ecsTaskExecutionRole` | Pull image, write logs | `AmazonECSTaskExecutionRolePolicy`, read Secrets Manager ARNs used by task defs |
| `playbookiqApiTaskRole` | Runtime API | `s3:PutObject/GetObject/DeleteObject` on uploads bucket prefix; `secretsmanager:GetSecretValue` for app secrets; **no** `*` on `s3:*` |
| `playbookiqWorkerTaskRole` | Celery | Same S3 + secrets as API; no admin |
| Human deployer | CI/CD | OIDC role for GitHub Actions: `ecs:UpdateService`, `iam:PassRole` only for task roles, no blanket `AdministratorAccess` |

RDS and Redis are reachable only from the ECS task security groups (SG-to-SG rules on 5432 / 6379).

---

## 2. Minimum sizes that can run PlaybookIQ (avoid OOM)

Sizing is based on this repo: FastAPI API, Celery **prefork** workers, full-season **pandas** `import_season` jobs (see M4 worker benchmark), Redis broker + cache (~256 MB cap locally in Compose), PostgreSQL with multi-season `plays` and analytics queries.

| Component | Do **not** use (why) | **Minimum viable** | **Typical student prod** |
| --- | --- | --- | --- |
| **API (Fargate)** | 0.25 vCPU / 0.5 GiB | **1 vCPU, 2 GiB** — Fargate minimum memory for 1 vCPU; enough for FastAPI + connection pools | Same |
| **Worker (Fargate)** | 1 vCPU / 2 GiB with `WORKER_CONCURRENCY=2` | **2 vCPU, 4 GiB**, **`WORKER_CONCURRENCY=1`** — one full-season import at a time (~1–3 GiB peak per process with Python/pandas overhead) | **2 vCPU, 8 GiB**, **`WORKER_CONCURRENCY=2`** (matches M4 local benchmark setup) |
| **Beat (Fargate)** | — | **0.25 vCPU, 0.5 GiB** | Same |
| **RDS** | `db.t4g.micro` (1 GiB) — tight for Postgres 16 + indexes + analytics on hundreds of thousands of plays | **`db.t4g.small` (2 GiB)**, Single-AZ, **50 GiB gp3** | **`db.t4g.medium` (4 GiB)**, **80 GiB gp3** |
| **ElastiCache** | — | **`cache.t4g.micro`** (~0.5 GiB; align with ~256 MB cache policy + broker) | **`cache.t4g.small`** (1.37 GiB) if queues back up during imports |
| **ALB + NAT** | Exposing RDS/Redis to the internet | **1 ALB**, **1 NAT Gateway** in a single AZ | Same |

**Worker memory note:** M4 scaled imports with **2 concurrent** full-season jobs on a **16 GiB** dev machine. On Fargate, treat **4 GiB × one import** and **8 GiB × two imports** as conservative task sizes; scale vCPU/memory up if Celery workers exit with OOM during `import_season`.

---

## 3. Monthly cost summary (us-east-1, on-demand)

Assumptions: all services run **24×7** for the month (730 hours); **one** NAT Gateway; **low** ALB usage (~1 LCU-hour average); **30–50 GiB**/month through NAT (image pulls, nflverse downloads); static UI on **CloudFront Free**; **2** Secrets Manager secrets; modest logs and S3.

| | **Monthly low** | **Monthly typical** |
| ---: | ---: | ---: |
| **Total (rounded)** | **~$229** | **~$282** |

### Line-item breakdown

| Line item | Rate (us-east-1) | Low ($/mo) | Typical ($/mo) |
| --- | --- | ---: | ---: |
| Fargate API 1 vCPU / 2 GiB | $0.04048/vCPU-hr + $0.004445/GiB-hr | 36.04 | 36.04 |
| Fargate worker | see sizing table | 72.08 (2 vCPU / 4 GiB) | 85.06 (2 vCPU / 8 GiB) |
| Fargate beat 0.25 vCPU / 0.5 GiB | same Fargate rates | 9.01 | 9.01 |
| RDS PostgreSQL | db.t4g.small **$0.032/hr** / medium **$0.064/hr** | 23.36 | 46.72 |
| RDS storage gp3 | **~$0.115/GiB-mo** (50 / 80 GiB) | 5.75 | 9.20 |
| ElastiCache Redis | micro **$0.016/hr** / small **$0.032/hr** | 11.68 | 23.36 |
| NAT Gateway | **$0.045/hr** + **$0.045/GiB** processed | 34.20 | 35.10 |
| Application Load Balancer | **$0.0225/hr** + **$0.008/LCU-hr** | 22.27 | 22.27 |
| Public IPv4 (NAT + ALB addresses) | **$0.005/hr** per address (×3) | 10.95 | 10.95 |
| Secrets Manager | **$0.40/secret/mo** | 0.80 | 0.80 |
| CloudWatch Logs | ~$0.50/GiB ingest (2 GiB assumed) | 1.00 | 1.00 |
| S3 + ECR (light student use) | storage + transfer | ~2.00 | ~2.00 |
| CloudFront Free (UI) | $0 flat plan | 0.00 | 0.00 |

Fargate math example (API): \((1 × 0.04048 + 2 × 0.004445) × 730 ≈ \$36.04\).

**Not included:** Route 53 hosted zone ($0.50/mo if you use a zone outside CloudFront Free DNS), data transfer out to internet beyond CloudFront allowances, AWS Support, tax, or **Multi-AZ** RDS. **Fargate Spot** for workers can cut worker compute up to ~70% but adds interruption risk ([Fargate pricing](https://aws.amazon.com/fargate/pricing/)).

---

## 4. AWS Free Tier and what still bills

AWS has **two** Free Tier shapes; confirm which applies to your account in the [AWS Free Tier](https://aws.amazon.com/free/) console.

### Accounts with classic 12-month Free Tier (and eligible services)

| Benefit | What it covers | Duration | Applies to this stack? |
| --- | --- | --- | --- |
| RDS | 750 hrs/mo on select **Single-AZ** instance types + **20 GiB gp2/gp3** + 20 GiB backup storage | 12 months | Partially — may offset a **micro/small** instance hours if the instance class is eligible; **storage above 20 GiB still bills** |
| ElastiCache | 750 hrs/mo **cache.t3.micro** (legacy text on pricing page) | 12 months (pre–15 Jul 2025 signups) | Only if you run an eligible micro node |
| Elastic Load Balancing | 750 hrs/mo shared ALB/CLB + 15 LCU-hrs for ALB | 12 months | Can offset **part** of ALB base/LCU |
| EC2 Free Tier | 750 hrs/mo **t2/t3.micro** + 750 hrs public IPv4 with EC2 | 12 months | **Does not** cover NAT, ALB, or Fargate |
| S3 | 5 GiB Standard storage (legacy) | 12 months | Small help for UI bucket |
| Data transfer | 15 GiB out to internet/mo (aggregated) | 12 months | Small help |

### Accounts on the newer Free Tier (from 15 July 2025)

- **$100–$200 account credits** for **6–12 months** on eligible usage ([S3 Free Tier text](https://aws.amazon.com/s3/pricing/), [ElastiCache pricing](https://aws.amazon.com/elasticache/pricing/)).
- Credits apply until exhausted; then **on-demand rates below apply in full**.

### What **keeps billing** even when “on Free Tier”

These are the usual surprises for students:

1. **NAT Gateway** — ~**$33/mo** hourly **plus** per-GB processing ([VPC pricing](https://aws.amazon.com/vpc/pricing/)) — **not** covered by Free Tier.
2. **Fargate** — API, worker, beat task CPU/memory hours — **not** covered by classic Free Tier.
3. **Public IPv4** on ALB and NAT — **$0.005/hr** each ([VPC pricing](https://aws.amazon.com/vpc/pricing/)); ALB/NAT addresses are **not** the EC2 Free Tier IPv4 allowance.
4. **RDS/ElastiCache** — hours beyond 750 or instance classes outside the offer; **storage** and **backup** beyond 20 GiB; **CPU surplus credits** on T4g if sustained high CPU ([RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/)).
5. **Secrets Manager** — per-secret monthly fee.
6. **CloudWatch Logs** — ingestion and storage after free allowances.
7. **S3** — storage and requests after credits/Free Tier.

**First-month “credit-only” rough range:** With $100–200 credits, a **low** stack (~$229/mo) might be **fully covered for one month**; a **typical** stack (~$282/mo) may need **top-up after credits** unless you tear down or stop always-on networking.

---

## 5. Price sources (verify before you deploy)

| Service | Official pricing page |
| --- | --- |
| Amazon ECS on Fargate | https://aws.amazon.com/fargate/pricing/ |
| Amazon RDS for PostgreSQL | https://aws.amazon.com/rds/postgresql/pricing/ |
| Amazon ElastiCache | https://aws.amazon.com/elasticache/pricing/ |
| Amazon S3 | https://aws.amazon.com/s3/pricing/ |
| Amazon VPC (NAT, IPv4) | https://aws.amazon.com/vpc/pricing/ |
| Elastic Load Balancing (ALB) | https://aws.amazon.com/elasticloadbalancing/pricing/ |
| Amazon CloudWatch | https://aws.amazon.com/cloudwatch/pricing/ |
| AWS Secrets Manager | https://aws.amazon.com/secrets-manager/pricing/ |
| Amazon CloudFront | https://aws.amazon.com/cloudfront/pricing/ |
| AWS Free Tier | https://aws.amazon.com/free/ |

Use the [AWS Pricing Calculator](https://calculator.aws/) to clone this model with your exact GiB, NAT traffic, and log volume.

---

## 6. Teardown checklist

Run in **reverse dependency order** after you have backups you care about (exports, Terraform state).

1. **Scale ECS services to 0** (API, worker, beat) — stops Fargate task charges quickly.
2. **Delete ECS services** and **task definitions** (optional cleanup).
3. **Delete ALB** listeners, target groups, then load balancer — stops ALB + ALB public IPv4 charges.
4. **Delete NAT Gateway** and **release Elastic IPs** tied to NAT — stops the largest fixed networking cost.
5. **Delete RDS instance** (disable **final snapshot** only if you accept data loss) — stops RDS compute; delete **manual snapshots** or they keep billing.
6. **Delete ElastiCache cluster** — stop cache node hours.
7. **Empty and delete S3 buckets** (uploads, UI, logs, terraform state if applicable) — versioning and incomplete multipart uploads can linger charges.
8. **Delete Secrets Manager secrets** (schedule minimum recovery window or force delete in dev).
9. **Delete CloudWatch log groups** (retention otherwise stores data).
10. **Delete ECR repositories** (images accrue storage).
11. **Delete CloudFront distribution** (must disable first; wait for deployment).
12. **Remove VPC endpoints, security groups, subnets, IGW, VPC** after dependencies are gone.
13. **Delete Route 53 hosted zone** if created (small charge until records removed).
14. **Run `terraform destroy` / `cdk destroy`** if IaC exists — confirm **no** orphaned ENIs, ELBs, or NAT gateways in the VPC console.

### If you forget a step — what still costs money

| Left running | Keeps charging |
| --- | --- |
| NAT Gateway | ~$0.045/hr + data processed + its public IPv4 |
| ALB | ~$0.0225/hr + LCUs + public IPv4 |
| RDS instance | Instance hours + storage + backups/snapshots |
| ElastiCache node | Node hours |
| Fargate tasks / ECS services desired count > 0 | Full task vCPU/memory |
| Elastic IP (unattached) | Idle public IPv4 $0.005/hr |
| S3 buckets with data | Per-GB-month + requests |
| RDS **snapshots** | Backup storage per GiB-month |
| Secrets | Per secret per month |
| CloudWatch Logs | Ingested + stored GiB |
| ECR images | Storage |

**Billing guardrails:** set an [AWS Budgets](https://aws.amazon.com/aws-cost-management/aws-budgets/) alert (e.g. $50 / $100 / $200), enable Cost Anomaly Detection, and tag resources `Project=playbookiq` for cleanup queries.

---

## 7. Next step (after you approve implementation)

When you explicitly ask to start M5 **implementation**, the first deliverable should be IaC + a non-production deploy path—not production traffic on day one. **Do not provision** until that separate approval.

---

*Estimate prepared for PlaybookIQ Milestone 5 planning. Figures are rounded from public list prices; your invoice will vary with traffic, NAT volume, logs, and tax.*
