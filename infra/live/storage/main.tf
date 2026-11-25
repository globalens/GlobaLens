# The R2 buckets of Phase 1 (docs/design/p1.md §6). The first segment of a path in the design note
# is the bucket: `cdn/now.json` is the key `now.json` in the bucket `globalens-cdn`.
#
# Everything here carries prevent_destroy, and infra/policy refuses a change that removes it.
# Credentials: CLOUDFLARE_API_TOKEN, an account API token with "Workers R2 Storage: Edit" to
# apply, or "Workers R2 Storage: Read" to plan. It is never a variable, so it never appears in a
# plan.
provider "cloudflare" {}

locals {
  # Both nodes are in US West (master plan §17, question 17). R2 honours a location hint only when
  # a bucket is first created.
  location = "wnam"

  # R2's default lifecycle rule: abort a multipart upload 7 days after it starts. Any lifecycle
  # configuration replaces the default, so each bucket's configuration restates it.
  abort_incomplete_uploads = {
    id         = "abort-incomplete-multipart-uploads"
    enabled    = true
    conditions = { prefix = "" }
    abort_multipart_uploads_transition = {
      condition = { type = "Age", max_age = 604800 }
    }
  }
}

# GDELT's verified zips, content-addressed: `gdelt/{stream}/dt={date}/{md5}.zip`. Kept 7 days in
# P1, about 8.4 GB of R2's free 10 GB. In P2 the zips move to the free node's disk and this bucket
# goes away without touching the lake, which is why it is a bucket of its own (Q18).
resource "cloudflare_r2_bucket" "raw" {
  account_id    = var.cloudflare_account_id
  name          = "globalens-raw"
  location      = local.location
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_bucket_lifecycle" "raw" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.raw.name

  rules = [
    local.abort_incomplete_uploads,
    {
      id         = "delete-after-7-days"
      enabled    = true
      conditions = { prefix = "" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 604800 }
      }
    },
  ]

  lifecycle {
    prevent_destroy = true
  }
}

# The lake. `facts/` (IDs, places, languages, outlets, times, hashes) is kept forever; its bucket
# lock starts at the P1 close, not before (Q17), and is added to this file then. `display/`
# (titles and URLs) is kept, and is the layer that can be redacted. Private.
resource "cloudflare_r2_bucket" "lake" {
  account_id    = var.cloudflare_account_id
  name          = "globalens-lake"
  location      = local.location
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_bucket_lifecycle" "lake" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.lake.name
  rules       = [local.abort_incomplete_uploads]

  lifecycle {
    prevent_destroy = true
  }
}

# The data plane: everything the browser reads. `live/` holds the content-addressed shards,
# compactions, title indexes and manifests, deleted 48 hours after they are written: nothing
# refers to one more than about 25 hours after it is written (the 24-hour window and the open
# hour), and the publisher never rewrites a key that exists (README.md). `now.json`, `stats.json`,
# `cost.json`, `basemap/`, `geo/` and `preview/` are kept.
resource "cloudflare_r2_bucket" "cdn" {
  account_id    = var.cloudflare_account_id
  name          = "globalens-cdn"
  location      = local.location
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_bucket_lifecycle" "cdn" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.cdn.name

  rules = [
    local.abort_incomplete_uploads,
    {
      id         = "delete-live-after-48-hours"
      enabled    = true
      conditions = { prefix = "live/" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 172800 }
      }
    },
  ]

  lifecycle {
    prevent_destroy = true
  }
}

# The cdn bucket's public r2.dev address: the data plane's base until a domain exists
# (design note §12.1). Rate-limited, with no edge cache. The only public bucket.
resource "cloudflare_r2_managed_domain" "cdn" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.cdn.name
  enabled     = true

  lifecycle {
    prevent_destroy = true
  }
}

# The real fixture week and the frozen evaluation dumps: real headlines, so private, read and
# written only by CI and the owner (Q19; master plan §9).
resource "cloudflare_r2_bucket" "fixtures" {
  account_id    = var.cloudflare_account_id
  name          = "globalens-fixtures"
  location      = local.location
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_bucket_lifecycle" "fixtures" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.fixtures.name
  rules       = [local.abort_incomplete_uploads]

  lifecycle {
    prevent_destroy = true
  }
}
