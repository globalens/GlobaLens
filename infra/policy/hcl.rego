# Rules on the OpenTofu source, checked with no credentials and no network on every pull
# request. From the repository root (infra/policy/test.sh, run by `mise run check`):
#
#   conftest test --combine --policy infra/policy --namespace globalens.hcl infra/live/*/*.tf
#
# With --combine the input is [{"path": <file>, "contents": <the file, parsed>}], so a rule
# knows which stack a file belongs to. Paths are relative to the repository root. conftest's
# hcl2 parser turns every block into a list and every reference into a "${...}" string:
#
#   resource.<type>.<name> = [{..., "lifecycle": [{"prevent_destroy": true}]}]
#   terraform = [{"backend": {"s3": [{...}]}, "encryption": [{"state": [...], "plan": [...]}]}]
#
# policy/testdata/hcl/ holds a stack that breaks each rule, run through the real parser by
# policy/test.sh, so a parser change cannot make these rules pass in silence.
package globalens.hcl

# Stacks whose every resource is storage, or holds the state of storage.
storage_stacks := {"infra/live/bootstrap", "infra/live/storage"}

# Buckets anyone may read, by resource name: the data plane (docs/design/p1.md §6, §12.1).
# P4 adds the Shots bucket here; nothing else is ever public (the plan's Conftest list).
public_buckets := {"cdn"}

bucket_prefix := "globalens-"

# Rule 1. Every storage resource keeps prevent_destroy: every resource in the storage stacks,
# and every R2 resource anywhere (a module included). tofu then refuses any plan that would
# destroy one, and removing the guard is a change a reviewer sees.
deny contains msg if {
	some r in resources
	storage(r)
	not protected(r.block)
	msg := sprintf(
		"%s: %s.%s is storage and must keep lifecycle { prevent_destroy = true }",
		[r.path, r.type, r.name],
	)
}

# Rule 2. A stack with state encrypts its state and its saved plans, both enforced, with an
# aes_gcm method keyed by a key provider defined beside it. `tofu validate` does not look at the
# encryption block at all (a reference to a method that does not exist passes it), so this
# rule checks the references too.
deny contains msg if {
	some dir in stateful
	not encrypted(dir)
	msg := sprintf(
		concat("", [
			"%s: a stack with state must encrypt its state and plans: an encryption block whose ",
			"state and plan blocks both say enforced = true and name an aes_gcm method keyed by a ",
			"key provider defined in the same block",
		]),
		[dir],
	)
}

# Rule 3. The unencrypted method (meant for migrating plaintext state) is never written down,
# not even as a fallback: state and plans stay encrypted from the first apply.
deny contains msg if {
	some f in input
	some enc in encryption_blocks_of(f)
	enc.method.unencrypted
	msg := sprintf("%s: the unencrypted method is not allowed; state and plans stay encrypted", [f.path])
}

# Rule 4. Only the public buckets may be reached without credentials, through the r2.dev
# address or a custom domain. Real headlines sit in lake and fixtures. An `enabled` that is not
# literally false counts as on.
deny contains msg if {
	some r in resources
	r.type in {"cloudflare_r2_managed_domain", "cloudflare_r2_custom_domain"}
	not switched_off(r)
	not r.block.bucket_name in public_bucket_names
	msg := sprintf(
		"%s: %s.%s makes %v public; only %v may be public",
		[r.path, r.type, r.name, object.get(r.block, "bucket_name", "a bucket"), public_buckets],
	)
}

# Rule 5. A key provider's passphrase comes from the owner's escrow: a variable declared in the
# same stack with sensitive = true, ephemeral = true and no default. So the key is never in the
# repository, and never in a saved plan or in `tofu show -json`, which prints a sensitive
# variable that is not ephemeral in clear text.
deny contains msg if {
	some f in input
	some enc in encryption_blocks_of(f)
	some name, providers in enc.key_provider.pbkdf2
	some provider in providers
	not escrowed(folder(f.path), object.get(provider, "passphrase", ""))
	msg := sprintf(
		concat("", [
			"%s: the pbkdf2 key provider %q must take its passphrase from a variable declared in ",
			"the same stack with sensitive = true, ephemeral = true and no default",
		]),
		[f.path, name],
	)
}

# Rule 6. A stack keeps its state in R2 under its own folder's name, with locking on. Two stacks
# sharing a key would each plan to destroy the other's resources.
deny contains msg if {
	some f in input
	dir := folder(f.path)
	stack_root(dir)
	some block in f.contents.terraform
	some s3 in block.backend.s3
	want := sprintf("%s/terraform.tfstate", [last_part(dir)])
	not locked_at(s3, want)
	msg := sprintf(
		"%s: the state key must be %q, with use_lockfile = true (one key per stack, named after its folder)",
		[f.path, want],
	)
}

deny contains msg if {
	some f in input
	stack_root(folder(f.path))
	some block in f.contents.terraform
	some type, _ in block.backend
	type != "s3"
	msg := sprintf("%s: a stack keeps its state in R2 through the s3 backend, not a %q backend", [f.path, type])
}

# Rule 7. No Infrequent Access storage: R2's free allowance covers Standard storage only, so it
# would be a recurring cost (CLAUDE.md, "Money"; master plan §14).
deny contains msg if {
	some r in resources
	r.type == "cloudflare_r2_bucket"
	r.block.storage_class == "InfrequentAccess"
	msg := sprintf("%s: %s.%s uses Infrequent Access, which has no free allowance", [r.path, r.type, r.name])
}

deny contains msg if {
	some r in resources
	r.type == "cloudflare_r2_bucket_lifecycle"
	some rule in r.block.rules
	count(object.get(rule, "storage_class_transitions", [])) > 0
	msg := sprintf(
		"%s: %s.%s moves objects to Infrequent Access, which has no free allowance",
		[r.path, r.type, r.name],
	)
}

resources contains {"path": f.path, "type": type, "name": name, "block": block} if {
	some f in input
	some type, by_name in f.contents.resource
	some name, blocks in by_name
	some block in blocks
}

storage(r) if startswith(r.type, "cloudflare_r2_")

storage(r) if folder(r.path) in storage_stacks

protected(block) if {
	some lifecycle in block.lifecycle
	lifecycle.prevent_destroy == true
}

switched_off(r) if {
	r.type == "cloudflare_r2_managed_domain"
	r.block.enabled == false
}

public_bucket_names contains sprintf("${cloudflare_r2_bucket.%s.name}", [b]) if some b in public_buckets

public_bucket_names contains concat("", [bucket_prefix, b]) if some b in public_buckets

# The folder a file sits in, and the last part of a path.
folder(path) := concat("/", array.slice(parts, 0, count(parts) - 1)) if parts := split(path, "/")

last_part(path) := parts[count(parts) - 1] if parts := split(path, "/")

# A root module with its own state: infra/live/<stack>, or infra/burst.
stack_root(dir) if regex.match(`^infra/live/[^/]+$`, dir)

stack_root("infra/burst")

stateful contains dir if {
	some f in input
	dir := folder(f.path)
	stack_root(dir)
	declares_state(f.contents)
}

declares_state(contents) if contents.resource

declares_state(contents) if contents.data

declares_state(contents) if contents.module

declares_state(contents) if {
	some block in contents.terraform
	block.backend
}

encryption_blocks_of(f) := [enc |
	some block in f.contents.terraform
	some enc in block.encryption
]

encrypted(dir) if {
	some f in input
	folder(f.path) == dir
	some enc in encryption_blocks_of(f)
	enforced(enc, "state")
	enforced(enc, "plan")
}

enforced(enc, target) if {
	some b in enc[target]
	b.enforced == true
	name := referenced(`^\$\{method\.aes_gcm\.([A-Za-z0-9_-]+)\}$`, b.method)[0]
	some method in enc.method.aes_gcm[name]
	key := referenced(`^\$\{key_provider\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)\}$`, method.keys)
	enc.key_provider[key[0]][key[1]]
}

escrowed(dir, passphrase) if {
	name := referenced(`^\$\{var\.([A-Za-z0-9_-]+)\}$`, passphrase)[0]
	some f in input
	folder(f.path) == dir
	some declared in f.contents.variable[name]
	declared.sensitive == true
	declared.ephemeral == true
	not "default" in object.keys(declared)
}

locked_at(s3, key) if {
	s3.key == key
	s3.use_lockfile == true
}

# The captured groups of a "${...}" reference, if it matches.
referenced(pattern, ref) := array.slice(groups[0], 1, count(groups[0])) if {
	groups := regex.find_all_string_submatch_n(pattern, ref, 1)
	count(groups) == 1
}
