variable "cloudflare_account_id" {
  description = "The Cloudflare account that holds R2. Not a secret, and not committed: set TF_VAR_cloudflare_account_id (README.md)."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{32}$", var.cloudflare_account_id))
    error_message = "A Cloudflare account ID is 32 lowercase hexadecimal characters."
  }
}

# Ephemeral, so the passphrase is never stored in a saved plan and never printed by
# `tofu show -json`; a variable that is only sensitive is printed there in clear text.
variable "state_passphrase" {
  description = "The owner's escrowed passphrase, from which the state and plan encryption key is derived. Set TF_VAR_state_passphrase without echoing it (README.md)."
  type        = string
  sensitive   = true
  ephemeral   = true
}
