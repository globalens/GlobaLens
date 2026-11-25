package globalens.hcl_test

import data.globalens.hcl

# Inputs are shaped as conftest's hcl2 parser gives them under --combine (conftest parse
# --combine prints the same): blocks are lists, references are "${...}" strings.
# policy/testdata/hcl/ checks the same rules on real files, through the real parser.

file(path, contents) := {"path": path, "contents": contents}

resource(type, name, block) := {"resource": {type: {name: [block]}}}

protected := [{"prevent_destroy": true}]

with_lifecycle(block, lifecycle) := object.union(block, {"lifecycle": lifecycle})

bucket(name) := {"account_id": "${var.cloudflare_account_id}", "name": name}

protected_bucket := resource("cloudflare_r2_bucket", "cdn", with_lifecycle(bucket("globalens-cdn"), protected))

# The encryption block of infra/live/storage/versions.tf.
encryption := {
	"key_provider": {"pbkdf2": {"escrow": [{"passphrase": "${var.state_passphrase}"}]}},
	"method": {"aes_gcm": {"escrow": [{"keys": "${key_provider.pbkdf2.escrow}"}]}},
	"state": [{"enforced": true, "method": "${method.aes_gcm.escrow}"}],
	"plan": [{"enforced": true, "method": "${method.aes_gcm.escrow}"}],
}

encryption_without(key) := object.remove(encryption, [key])

encryption_with(key, value) := object.union(encryption, {key: value})

last_part(dir) := parts[count(parts) - 1] if parts := split(dir, "/")

backend(dir) := {"s3": [{
	"bucket": "globalens-tofu-state",
	"key": sprintf("%s/terraform.tfstate", [last_part(dir)]),
	"use_lockfile": true,
}]}

terraform_block(dir, enc) := {"required_version": "~> 1.13.0", "backend": backend(dir), "encryption": [enc]}

passphrase_variable := {"type": "${string}", "sensitive": true, "ephemeral": true}

versions(dir, enc) := file(concat("/", [dir, "versions.tf"]), {"terraform": [terraform_block(dir, enc)]})

variables(dir, passphrase) := file(concat("/", [dir, "variables.tf"]), {"variable": {"state_passphrase": [passphrase]}})

# A stack whose versions.tf and variables.tf pass every rule, and one more file.
stack(dir, contents) := [
	versions(dir, encryption),
	variables(dir, passphrase_variable),
	file(concat("/", [dir, "main.tf"]), contents),
]

storage(contents) := stack("infra/live/storage", contents)

storage_encrypted_by(enc) := [
	versions("infra/live/storage", enc),
	variables("infra/live/storage", passphrase_variable),
	file("infra/live/storage/main.tf", protected_bucket),
]

messages(denies, part) := {m | some m in denies; contains(m, part)}

# --- 1. prevent_destroy on storage ---

test_a_protected_bucket_in_the_storage_stack_passes if {
	count(hcl.deny) == 0 with input as storage(protected_bucket)
}

test_a_bucket_without_prevent_destroy_is_denied if {
	denies := hcl.deny with input as storage(resource("cloudflare_r2_bucket", "lake", bucket("globalens-lake")))
	count(denies) == 1
	count(messages(denies, "cloudflare_r2_bucket.lake")) == 1
	count(messages(denies, "prevent_destroy")) == 1
}

test_prevent_destroy_false_is_denied if {
	denies := hcl.deny with input as storage(resource(
		"cloudflare_r2_bucket", "lake",
		with_lifecycle(bucket("globalens-lake"), [{"prevent_destroy": false}]),
	))
	count(messages(denies, "prevent_destroy")) == 1
}

test_a_lifecycle_block_without_prevent_destroy_is_denied if {
	denies := hcl.deny with input as storage(resource(
		"cloudflare_r2_bucket", "lake",
		with_lifecycle(bucket("globalens-lake"), [{"ignore_changes": "${[location]}"}]),
	))
	count(messages(denies, "prevent_destroy")) == 1
}

test_every_unprotected_resource_is_reported if {
	two := {"resource": {"cloudflare_r2_bucket": {
		"raw": [bucket("globalens-raw")],
		"lake": [bucket("globalens-lake")],
	}}}
	count(messages(hcl.deny, "prevent_destroy")) == 2 with input as storage(two)
}

test_an_r2_resource_needs_it_in_any_stack if {
	denies := hcl.deny with input as stack("infra/live/edge", resource(
		"cloudflare_r2_custom_domain", "cdn",
		{"bucket_name": "${cloudflare_r2_bucket.cdn.name}"},
	))
	count(messages(denies, "prevent_destroy")) == 1
}

test_an_r2_resource_in_a_module_needs_it if {
	denies := hcl.deny with input as [file(
		"infra/modules/bucket/main.tf",
		resource("cloudflare_r2_bucket", "this", bucket("${var.name}")),
	)]
	count(denies) == 1
	count(messages(denies, "prevent_destroy")) == 1
}

test_every_resource_in_a_storage_stack_needs_it if {
	every dir in ["infra/live/storage", "infra/live/bootstrap"] {
		denies := hcl.deny with input as stack(dir, resource("terraform_data", "marker", {"input": "x"}))
		count(messages(denies, "terraform_data.marker")) == 1
	}
}

test_other_resources_outside_storage_may_be_destroyed if {
	count(hcl.deny) == 0 with input as stack("infra/live/web", resource("terraform_data", "marker", {"input": "x"}))
}

# --- 2 and 3. State and plan encryption ---

test_a_stack_with_state_and_no_encryption_is_denied if {
	denies := hcl.deny with input as [
		file("infra/live/storage/versions.tf", {"terraform": [{"required_version": "~> 1.13.0"}]}),
		file("infra/live/storage/main.tf", protected_bucket),
	]
	count(denies) == 1
	count(messages(denies, "infra/live/storage: a stack with state must encrypt")) == 1
}

test_state_and_plan_must_both_be_enforced if {
	every bad in [
		encryption_without("state"),
		encryption_without("plan"),
		encryption_with("state", [{"enforced": false, "method": "${method.aes_gcm.escrow}"}]),
		encryption_with("plan", [{"method": "${method.aes_gcm.escrow}"}]),
	] {
		count(messages(hcl.deny, "must encrypt")) == 1 with input as storage_encrypted_by(bad)
	}
}

test_the_method_must_be_a_defined_aes_gcm_method if {
	every bad in [
		encryption_with("state", [{"enforced": true, "method": "${method.aes_gcm.other}"}]),
		encryption_with("plan", [{"enforced": true, "method": "${method.foo.escrow}"}]),
		encryption_with("method", {"aes_gcm": {"escrow": [{"keys": "${key_provider.pbkdf2.missing}"}]}}),
		encryption_with("method", {"aes_gcm": {"escrow": [{}]}}),
	] {
		count(messages(hcl.deny, "must encrypt")) == 1 with input as storage_encrypted_by(bad)
	}
}

test_encryption_may_sit_in_any_file_of_the_stack if {
	count(hcl.deny) == 0 with input as [
		file("infra/live/storage/backend.tf", {"terraform": [terraform_block("infra/live/storage", encryption)]}),
		file("infra/live/storage/versions.tf", {"terraform": [{"required_version": "~> 1.13.0"}]}),
		variables("infra/live/storage", passphrase_variable),
		file("infra/live/storage/main.tf", protected_bucket),
	]
}

test_another_stacks_encryption_does_not_count if {
	denies := hcl.deny with input as [
		versions("infra/live/edge", encryption),
		file("infra/live/storage/main.tf", protected_bucket),
	]
	count(messages(denies, "infra/live/storage: a stack with state must encrypt")) == 1
}

test_a_placeholder_stack_needs_no_encryption if {
	count(hcl.deny) == 0 with input as [file(
		"infra/live/web/versions.tf",
		{"terraform": [{"required_version": "~> 1.13.0"}]},
	)]
}

test_a_backend_data_source_or_module_also_means_state if {
	every contents in [
		{"terraform": [{"backend": backend("infra/live/web")}]},
		{"data": {"cloudflare_r2_bucket": {"cdn": [{"bucket_name": "globalens-cdn"}]}}},
		{"module": {"site": [{"source": "../../modules/site"}]}},
	] {
		count(messages(hcl.deny, "must encrypt")) == 1 with input as [file("infra/live/web/main.tf", contents)]
	}
}

test_burst_is_a_stack_too if {
	denies := hcl.deny with input as [file("infra/burst/main.tf", resource("terraform_data", "m", {"input": "x"}))]
	count(messages(denies, "infra/burst: a stack with state must encrypt")) == 1
}

test_a_module_is_not_a_stack if {
	count(hcl.deny) == 0 with input as [file("infra/modules/site/main.tf", resource("terraform_data", "m", {"input": "x"}))]
}

test_the_unencrypted_method_is_never_allowed if {
	fallback := encryption_with("method", {
		"aes_gcm": {"escrow": [{"keys": "${key_provider.pbkdf2.escrow}"}]},
		"unencrypted": {"migrate": [{}]},
	})
	denies := hcl.deny with input as storage_encrypted_by(fallback)
	count(denies) == 1
	count(messages(denies, "unencrypted")) == 1
}

# --- 4. Only the cdn bucket is public ---

r2_dev(bucket_name, enabled) := resource("cloudflare_r2_managed_domain", "public", {
	"account_id": "${var.cloudflare_account_id}",
	"bucket_name": bucket_name,
	"enabled": enabled,
	"lifecycle": protected,
})

custom_domain(bucket_name) := resource("cloudflare_r2_custom_domain", "public", {
	"bucket_name": bucket_name,
	"domain": "cdn.example.org",
	"lifecycle": protected,
})

test_the_cdn_bucket_may_be_public if {
	every contents in [
		r2_dev("${cloudflare_r2_bucket.cdn.name}", true),
		r2_dev("globalens-cdn", true),
		custom_domain("${cloudflare_r2_bucket.cdn.name}"),
	] {
		count(hcl.deny) == 0 with input as storage(contents)
	}
}

test_no_other_bucket_may_be_public if {
	every contents in [
		r2_dev("${cloudflare_r2_bucket.lake.name}", true),
		r2_dev("${cloudflare_r2_bucket.fixtures.id}", true),
		r2_dev("globalens-fixtures", true),
		r2_dev("${cloudflare_r2_bucket.cdn.name}-copy", true),
		r2_dev("${cloudflare_r2_bucket.lake.name}", "${var.public}"),
		custom_domain("${cloudflare_r2_bucket.lake.name}"),
	] {
		count(messages(hcl.deny, "public")) == 1 with input as storage(contents)
	}
}

test_a_switched_off_r2_dev_address_is_not_public if {
	count(hcl.deny) == 0 with input as storage(r2_dev("${cloudflare_r2_bucket.lake.name}", false))
}

# --- 5. The passphrase comes from the owner's escrow, never from the code ---

storage_with_passphrase(passphrase, declared) := [
	versions("infra/live/storage", encryption_with("key_provider", {"pbkdf2": {"escrow": [{"passphrase": passphrase}]}})),
	variables("infra/live/storage", declared),
	file("infra/live/storage/main.tf", protected_bucket),
]

test_the_passphrase_comes_from_an_escrowed_variable if {
	count(hcl.deny) == 0 with input as storage_with_passphrase("${var.state_passphrase}", passphrase_variable)
}

test_a_passphrase_written_in_the_code_is_denied if {
	denies := hcl.deny with input as storage_with_passphrase("not-a-real-key-but-in-the-code", passphrase_variable)
	count(denies) == 1
	count(messages(denies, "passphrase")) == 1
}

test_the_variable_is_sensitive_ephemeral_and_has_no_default if {
	every declared in [
		object.remove(passphrase_variable, ["ephemeral"]),
		object.remove(passphrase_variable, ["sensitive"]),
		object.union(passphrase_variable, {"ephemeral": false}),
		object.union(passphrase_variable, {"default": "not-a-real-key-0000"}),
	] {
		count(messages(hcl.deny, "passphrase")) == 1 with input as storage_with_passphrase("${var.state_passphrase}", declared)
	}
}

test_the_variable_is_declared_in_the_same_stack if {
	denies := hcl.deny with input as [
		versions("infra/live/storage", encryption),
		variables("infra/live/edge", passphrase_variable),
		file("infra/live/storage/main.tf", protected_bucket),
	]
	count(messages(denies, "infra/live/storage/versions.tf: the pbkdf2 key provider")) == 1
}

test_a_key_provider_without_a_passphrase_is_denied if {
	no_passphrase := encryption_with("key_provider", {"pbkdf2": {"escrow": [{}]}})
	count(messages(hcl.deny, "passphrase")) == 1 with input as storage_encrypted_by(no_passphrase)
}

# --- 6. One locked state key per stack, in R2 ---

storage_with_backend(b) := [
	file("infra/live/storage/versions.tf", {"terraform": [object.union(
		terraform_block("infra/live/storage", encryption),
		{"backend": b},
	)]}),
	variables("infra/live/storage", passphrase_variable),
	file("infra/live/storage/main.tf", protected_bucket),
]

test_each_stack_keeps_its_own_locked_state_key if {
	every b in [
		{"s3": [{"bucket": "globalens-tofu-state", "key": "bootstrap/terraform.tfstate", "use_lockfile": true}]},
		{"s3": [{"bucket": "globalens-tofu-state", "key": "storage/terraform.tfstate"}]},
		{"s3": [{"bucket": "globalens-tofu-state", "key": "storage/terraform.tfstate", "use_lockfile": false}]},
		{"s3": [{"bucket": "globalens-tofu-state", "use_lockfile": true}]},
	] {
		count(messages(hcl.deny, "state key")) == 1 with input as storage_with_backend(b)
	}
}

test_a_stack_keeps_its_state_in_r2 if {
	denies := hcl.deny with input as storage_with_backend({"local": [{"path": "terraform.tfstate"}]})
	count(denies) == 1
	count(messages(denies, "s3 backend")) == 1
}

test_the_burst_state_key_is_its_folder_name if {
	count(hcl.deny) == 0 with input as stack("infra/burst", resource("terraform_data", "m", {"input": "x"}))
}

# --- 7. No Infrequent Access storage ---

test_infrequent_access_is_never_used if {
	every contents in [
		resource("cloudflare_r2_bucket", "cdn", with_lifecycle(
			object.union(bucket("globalens-cdn"), {"storage_class": "InfrequentAccess"}),
			protected,
		)),
		resource("cloudflare_r2_bucket_lifecycle", "cdn", {
			"bucket_name": "${cloudflare_r2_bucket.cdn.name}",
			"rules": [{
				"id": "to-infrequent-access",
				"enabled": true,
				"conditions": {"prefix": ""},
				"storage_class_transitions": [{
					"condition": {"type": "Age", "max_age": 2592000},
					"storage_class": "InfrequentAccess",
				}],
			}],
			"lifecycle": protected,
		}),
	] {
		count(messages(hcl.deny, "Infrequent Access")) == 1 with input as storage(contents)
	}
}

test_standard_storage_passes if {
	count(hcl.deny) == 0 with input as storage(resource("cloudflare_r2_bucket", "cdn", with_lifecycle(
		object.union(bucket("globalens-cdn"), {"storage_class": "Standard"}),
		protected,
	)))
}
