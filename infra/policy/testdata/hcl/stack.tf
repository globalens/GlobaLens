# A stack that passes every rule of infra/policy/hcl.rego, in one file. policy/tests copies it to
# infra/live/storage/main.tf in a scratch folder, breaks one rule at a time, and checks that
# conftest's real HCL parser and the policy refuse each copy with the expected message.
terraform {
  required_version = "~> 1.13.0"

  backend "s3" {
    bucket       = "globalens-tofu-state"
    key          = "storage/terraform.tfstate"
    use_lockfile = true
  }

  encryption {
    key_provider "pbkdf2" "escrow" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "escrow" {
      keys = key_provider.pbkdf2.escrow
    }
    state {
      method   = method.aes_gcm.escrow
      enforced = true
    }
    plan {
      method   = method.aes_gcm.escrow
      enforced = true
    }
  }
}

variable "state_passphrase" {
  type      = string
  sensitive = true
  ephemeral = true
}

resource "cloudflare_r2_bucket" "cdn" {
  account_id = "00000000000000000000000000000000"
  name       = "globalens-cdn"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_managed_domain" "cdn" {
  account_id  = "00000000000000000000000000000000"
  bucket_name = cloudflare_r2_bucket.cdn.name
  enabled     = true

  lifecycle {
    prevent_destroy = true
  }
}
