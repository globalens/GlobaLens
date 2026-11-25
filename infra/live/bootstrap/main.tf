# Credentials: CLOUDFLARE_API_TOKEN, an account API token with "Workers R2 Storage: Edit"
# (README.md). It is never a variable, so it never appears in a plan.
provider "cloudflare" {}

# Every stack's state, one key per stack, named after the stack's folder. Private: no r2.dev
# address and no custom domain. R2 has no object versioning, so the bucket holds the current state
# of each stack and nothing older.
resource "cloudflare_r2_bucket" "state" {
  account_id = var.cloudflare_account_id
  name       = "globalens-tofu-state"
  # Both nodes are in US West (master plan §17, question 17). R2 honours a location hint only when
  # a bucket is first created.
  location      = "wnam"
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

# Written out so that a rule added by hand (an expiry rule would delete state) shows up as drift.
# Any lifecycle configuration replaces R2's default rule, so the default is restated.
resource "cloudflare_r2_bucket_lifecycle" "state" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.state.name

  rules = [{
    id         = "abort-incomplete-multipart-uploads"
    enabled    = true
    conditions = { prefix = "" }
    # 7 days, R2's default.
    abort_multipart_uploads_transition = {
      condition = { type = "Age", max_age = 604800 }
    }
  }]

  lifecycle {
    prevent_destroy = true
  }
}
