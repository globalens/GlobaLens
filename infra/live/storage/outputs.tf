output "buckets" {
  description = "Bucket names by the first segment of the design note's paths: `cdn/now.json` is `now.json` in buckets.cdn."
  value = {
    raw      = cloudflare_r2_bucket.raw.name
    lake     = cloudflare_r2_bucket.lake.name
    cdn      = cloudflare_r2_bucket.cdn.name
    fixtures = cloudflare_r2_bucket.fixtures.name
  }
}

output "cdn_r2_dev_domain" {
  description = "The cdn bucket's r2.dev host: the data plane's base until a domain exists (design note §12.1)."
  value       = cloudflare_r2_managed_domain.cdn.domain
}
