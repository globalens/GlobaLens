# infra/live/bootstrap

The R2 bucket that holds every stack's OpenTofu state, `globalens-tofu-state`, with OpenTofu's
client-side state encryption. The owner applies it once, from their own machine: the only
production change that does not go through CI (design note §9, task 6; §11). Its state then
moves into the bucket it created, and from there it is planned like every other stack.

Nothing here has been applied. The steps below need R2 enabled on the Cloudflare account first:
its $0 plan asks for a card on file, a step the owner has deferred until this task needs it.

## How the state is kept

- Each stack's state is one object, `<stack>/terraform.tfstate`, named after the stack's folder.
  While a run writes it, `<stack>/terraform.tfstate.tflock` holds the lock (a conditional write,
  which R2 supports).
- State and saved plans are encrypted with AES-GCM before they leave the machine, under a key
  derived (PBKDF2) from one passphrase. `enforced = true`: OpenTofu refuses to write either one
  unencrypted.
- The passphrase is an ephemeral variable, so it is never stored in a saved plan and never
  printed by `tofu show -json`. A variable that is only `sensitive` is printed there in clear
  text: this was checked on 25 November 2026, and `infra/policy` refuses one.
- R2 has no object versioning, so the bucket keeps only the current state of each stack. A lost
  or damaged state is rebuilt by importing the resources, which survive because they carry
  `prevent_destroy`. Losing the passphrase loses every state in the same way, so it is escrowed.

## Escrow (the owner, once, before anything else)

Claude never generates, sees or stores the passphrase or the key.

1. **Check age.** On this Mac, mise 2025.4.0 installs age without checking a checksum or a
   signature. The installed age 1.3.2 was checked by hand on 25 November 2026 against its GitHub
   build attestation (ADR-0013). On another machine, check the release archive before using it:
   `gh attestation verify <archive> --repo FiloSottile/age`.
2. **Make the escrow key.** `mise exec -- age-keygen -o globalens-escrow.agekey` writes the key
   and prints its public half (`age1…`), which is not secret. Keep the file offline, in two
   places (a USB stick and a printout): never in the repository, a synced folder or a chat.
3. **Make the state passphrase** with your password manager's generator: at least 32 random
   characters (OpenTofu requires at least 16). Save it as "GlobaLens OpenTofu state passphrase".
4. **Escrow a copy, encrypted to the key.** Paste the passphrase at the silent prompt of:

   ```bash
   read -rs pass && printf '%s' "$pass" | mise exec -- age -r age1PUBLICKEY -o globalens-state-passphrase.age && unset pass
   ```

   with your public key in place of `age1PUBLICKEY`. Keep `globalens-state-passphrase.age` with
   the key's printout. To recover the passphrase:
   `mise exec -- age -d -i globalens-escrow.agekey globalens-state-passphrase.age`.

The plan escrows a third secret the same way when Phase 4 needs it: the backup cipher passphrase.

## Credentials (the owner, in the Cloudflare dashboard)

- **The account ID:** 32 hexadecimal characters, on the account's overview page. Not a secret,
  and not committed: each run reads it from `TF_VAR_cloudflare_account_id`.
- **A bootstrap API token:** an account API token for this account only, with the permission
  "Workers R2 Storage: Edit", expiring the next day. The provider reads it from
  `CLOUDFLARE_API_TOKEN`. Delete it when the bootstrap is done.
- **An R2 API token for the state bucket**, made after step 1 below: R2, "Manage API tokens",
  "Object Read & Write" on `globalens-tofu-state` only. Its access key ID and secret are the
  backend's S3 credentials, read from `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

## The bootstrap (the owner, from a clean checkout of `main`)

At the repository root, enter each secret at a silent prompt so it never reaches the shell's
history:

```bash
read -rs CLOUDFLARE_API_TOKEN && export CLOUDFLARE_API_TOKEN
read -rs TF_VAR_state_passphrase && export TF_VAR_state_passphrase
export TF_VAR_cloudflare_account_id=YOUR_ACCOUNT_ID
cd infra/live/bootstrap
```

1. **First apply, with a local backend**, because the bucket the backend names does not exist
   yet. `override.tf` replaces the backend for this one run, and git ignores it.

   ```bash
   printf 'terraform {\n  backend "local" {}\n}\n' > override.tf
   mise exec -- tofu init -input=false
   mise exec -- tofu plan -out=bootstrap.tfplan
   mise exec -- tofu apply bootstrap.tfplan
   ```

   The plan creates two resources, `cloudflare_r2_bucket.state` and
   `cloudflare_r2_bucket_lifecycle.state`, and nothing else. The local `terraform.tfstate` it
   writes is already encrypted.
2. **Make the R2 API token for the state bucket** (above), and enter its two halves:

   ```bash
   read -rs AWS_ACCESS_KEY_ID && export AWS_ACCESS_KEY_ID
   read -rs AWS_SECRET_ACCESS_KEY && export AWS_SECRET_ACCESS_KEY
   ```

3. **Move the state into the bucket**, check it, and remove the local copies:

   ```bash
   rm override.tf
   mise exec -- tofu init -input=false -migrate-state -force-copy
   mise exec -- tofu plan
   rm -f terraform.tfstate terraform.tfstate.backup bootstrap.tfplan
   ```

   The last plan must say "No changes".
4. **Finish.** Delete the bootstrap API token in the dashboard and close the terminal, which
   takes the variables with it.

CI's protected `production` environment (task 16) then needs: the account ID, the passphrase,
read-only tokens for plans (Cloudflare "Workers R2 Storage: Read" and R2 "Object Read" on the
state bucket), and the tokens its apply job uses.

## Rotating the passphrase

OpenTofu decrypts with a fallback method while state is re-encrypted:

1. Add a key provider and a method for the new passphrase (a second ephemeral variable), point
   `state` and `plan` at the new method, and add `fallback { method = method.aes_gcm.escrow }`
   to both.
2. Plan and apply every stack, through CI: each state is written again under the new key.
3. Remove the fallback and the old method, escrow the new passphrase, and destroy the old copy.

## Checks

- `mise run check`: the Conftest policies in `infra/policy` with their tests, `tofu fmt`, ruff,
  pyright and pytest. No credentials, no network.
- `mise run tofu:validate`: `init -backend=false` and `validate` for every stack. It downloads
  the providers each lock file pins.
- `mise run tofu:plan`: a real plan of every stack, read-only, each checked by
  `infra/policy/check-plan.sh`. It needs the four variables above and read-only tokens, and it
  never applies.
