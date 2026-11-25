terraform {
  required_version = "~> 1.13.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.29.0"
    }
  }

  # This stack creates the bucket its own backend names. Its first apply therefore runs once,
  # from the owner's machine, with a local backend; its state then moves into the bucket
  # (README.md). Every other stack's state is in that bucket from the start.
  #
  # The settings are those of Cloudflare's guide to R2 as an S3 remote backend. Credentials come
  # from AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY: an R2 API token scoped to this one bucket.
  # use_lockfile locks with a conditional write (If-None-Match), which R2 supports.
  backend "s3" {
    bucket       = "globalens-tofu-state"
    key          = "bootstrap/terraform.tfstate"
    region       = "auto"
    use_lockfile = true
    endpoints = {
      s3 = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com"
    }
    use_path_style              = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }

  # State and saved plans are encrypted on the machine that runs OpenTofu, before they are
  # written anywhere, with a key derived from the owner's escrowed passphrase (README.md,
  # "Escrow"). enforced = true makes OpenTofu refuse to write either one unencrypted.
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
