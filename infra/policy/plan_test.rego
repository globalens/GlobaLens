package globalens.plan_test

import data.globalens.plan

# One resource change, shaped like `tofu show -json` output (policy/testdata/plan_mixed/plan.json).
change(address, actions) := {
	"address": address,
	"mode": "managed",
	"type": "terraform_data",
	"name": address,
	"change": {"actions": actions},
}

# conftest --combine input: one document per plan, with the path it was given.
combined(path, changes) := [{"path": path, "contents": {"format_version": "1.2", "resource_changes": changes}}]

live := "infra/live/storage/tfplan.json"

burst := "infra/burst/scratch/tfplan.json"

test_a_delete_outside_burst_is_denied if {
	denies := plan.deny with input as combined(live, [change("cloudflare_r2_bucket.lake", ["delete"])])
	count(denies) == 1
	some msg in denies
	contains(msg, "cloudflare_r2_bucket.lake")
	contains(msg, live)
}

test_a_replacement_is_a_destroy if {
	denies := plan.deny with input as combined(live, [
		change("a", ["delete", "create"]),
		change("b", ["create", "delete"]),
	])
	count(denies) == 2
}

test_changes_that_destroy_nothing_pass if {
	denies := plan.deny with input as combined(live, [
		change("created", ["create"]),
		change("updated", ["update"]),
		change("unchanged", ["no-op"]),
		change("read", ["read"]),
		change("forgotten", ["forget"]),
	])
	count(denies) == 0
}

test_a_plan_with_no_changes_passes if {
	count(plan.deny) == 0 with input as [{"path": live, "contents": {"format_version": "1.2"}}]
}

test_a_burst_stack_may_destroy if {
	count(plan.deny) == 0 with input as combined(burst, [change("hcloud_server.a", ["delete"])])
}

test_every_path_outside_burst_is_denied if {
	every path in [
		"infra/burster/x/tfplan.json",
		"infra/live/burst/tfplan.json",
		"burst/tfplan.json",
		"./infra/burst/x/tfplan.json",
		"/home/runner/work/GlobaLens/infra/burst/x/tfplan.json",
	] {
		count(plan.deny) == 1 with input as combined(path, [change("a", ["delete"])])
	}
}

test_a_plan_given_without_a_path_counts_as_outside_burst if {
	bare := {"format_version": "1.2", "resource_changes": [change("a", ["delete"])]}
	denies := plan.deny with input as bare
	count(denies) == 1
	some msg in denies
	contains(msg, "no path")
}

test_each_plan_is_judged_by_its_own_path if {
	denies := plan.deny with input as array.concat(
		combined(burst, [change("burst_only", ["delete"])]),
		combined(live, [change("live_only", ["delete"])]),
	)
	count(denies) == 1
	some msg in denies
	contains(msg, "live_only")
}

# Real OpenTofu 1.13.9 output (policy/testdata/make-plans.sh), loaded with --data policy/testdata.

test_real_plan_denies_exactly_the_destroys if {
	denies := plan.deny with input as [{"path": live, "contents": data.plan_mixed}]
	count(denies) == 3
	every address in ["terraform_data.gone", "terraform_data.replaced", "terraform_data.cbd"] {
		some msg in denies
		contains(msg, sprintf("destroys %s ", [address]))
	}
}

test_real_destroy_plan_denies_every_resource if {
	count(plan.deny) == 5 with input as [{"path": live, "contents": data.plan_destroy}]
}

test_real_destroy_plan_passes_in_burst if {
	count(plan.deny) == 0 with input as [{"path": burst, "contents": data.plan_destroy}]
}
