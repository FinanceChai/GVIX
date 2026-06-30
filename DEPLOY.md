# Deploying GVIX to the Charts & Parts AWS estate

GVIX is a **Streamlit** app — it needs a long-running Python web server (it can't be
static), so it maps to the estate's **Elastic Beanstalk** pattern (`eb-application`),
not the S3/CloudFront one. EB gives it an ALB + HTTPS + health checks, the same way
the Strapi backend is hosted.

The app is already EB-ready (in this folder):

| File | Purpose |
|------|---------|
| `Procfile` | `web:` runs Streamlit on port 8000, headless, CORS/XSRF off (behind the proxy) |
| `.platform/nginx/conf.d/websocket_upgrade.conf` | http-level `map` for WebSocket `Connection: upgrade` |
| `.platform/nginx/conf.d/elasticbeanstalk/streamlit.conf` | proxies `/_stcore/stream` (WebSocket) and `/_stcore/health` |
| `requirements.txt` | runtime deps (`streamlit>=1.40`, pandas, plotly, yfinance, numpy) |
| `.ebignore` | keeps `.venv/` etc. out of the deploy bundle |

Verified locally: `GET /_stcore/health → 200 ok`, `GET / → 200`.

> Prereqs: AWS CLI profile `charts-and-parts`; the shared `vpc`, `ssl-certificate`, and
> `iam-open-id` modules applied (GVIX reads `vpc_id`, `public_subnet_ids`,
> `ssl_cert_arn` from SSM). An EC2 key pair for SSH.

## 1. The EB module is already scaffolded

A **slim** EB module for GVIX has been created and `terraform validate`d at:

```
charts-and-parts-terraform/eb-application-gvix/prod/
```

It is the `eb-application` module adapted for Streamlit (the original couples to
Strapi/Postgres/Mailgun via `deploy-test-app.tf`, which GVIX doesn't need):
- `deploy-test-app.tf`, `deployer-iam.tf`, `deployer-policy.json` and the artifact
  S3 bucket were removed.
- `locals.tf` provides a minimal `app_env` (`GVIX_SITE_URL` only).
- The hardcoded resource names were renamed so they **don't collide** with the
  backend's EB app: IAM role → `${project}-gvix-beanstalk-role`, instance profile →
  `${project}-gvix-beanstalk-instance-profile`, EB app → `${project}-gvix-app`.
- `terraform.tfvars` is set for `gvix-prod` / `gvix.chartsandparts.com`, `t3a.small`,
  health check `/_stcore/health`, and a Python solution stack.

**Before applying, confirm two values in `terraform.tfvars`:**
- `eb_platform` — the exact string drifts over time:
  `aws elasticbeanstalk list-available-solution-stacks --profile charts-and-parts | grep -i python`
- `ssh_key_name` and `vpc_environment` match a real key pair / VPC env.

Then apply (needs the `charts-and-parts` AWS credentials, which weren't available where
this was scaffolded — so it's validated but not yet planned against your account):
```bash
cd charts-and-parts-terraform/eb-application-gvix/prod
terraform init && terraform plan && terraform apply
```

## 2. Deploy the app bundle

EB serves the latest application version. Either via the EB CLI:
```bash
cd gvix_cp-main
eb init --profile charts-and-parts      # select the gvix EB application + region
eb deploy
```
…or zip-and-upload through the same Bitbucket-OIDC pipeline the backend uses
(zip the folder respecting `.ebignore`, push as a new EB application version).

## 3. DNS & cert

- Point `gvix.chartsandparts.com` at the EB environment's ALB. The `eb-application`
  module already has a commented Route53 alias block (`custom_app_domain`) — uncomment
  it and set the subdomain, or add an A-alias record to the env CNAME.
- The ALB HTTPS listener uses the wildcard ACM cert from SSM (`*.chartsandparts.com`) — already wired.

## 4. Health check & sessions

- Health check path is `/_stcore/health` (set above). EB/ALB will mark the instance healthy once Streamlit is up.
- The module runs a **single instance** (ASG min=max=1), so WebSocket session affinity
  is a non-issue. If you ever scale out, enable ALB stickiness.

## 5. Point the launcher at it

In the main webapp set `VITE_GVIX_URL=https://gvix.chartsandparts.com`
(see `charts-and-parts-webapp/.env.example`) and rebuild/redeploy the webapp.

## Note on SEO injection

`app.py`'s `inject_seo_meta()` patches Streamlit's static `index.html` at runtime
(writable on the EB instance), so crawler meta/OG tags work on EB. It no-ops silently
if the filesystem is read-only.
