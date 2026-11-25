output "state_bucket" {
  description = "The bucket that every stack's backend names."
  value       = cloudflare_r2_bucket.state.name
}
