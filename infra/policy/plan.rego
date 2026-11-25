# Rules on a saved plan, as `tofu show -json` prints it.
#
# mise run tofu:plan pipes each stack's plan here with the stack's path, relative to the
# repository root (nothing is written to disk):
#
#   tofu show -json <plan> | conftest test --combine --parser json --policy infra/policy \
#     --namespace globalens.plan --stdin-filename infra/live/<stack>/tfplan.json -
#
# With --combine the input is [{"path": ..., "contents": <the plan>}]. A plan passed without
# --combine has no path, and an absolute path does not start with infra/burst/: both count as
# outside it, so a mistake in how the policy is called refuses a destroy rather than allows one.
package globalens.plan

# CLAUDE.md: "Destroys target infra/burst only; never storage." A replacement is a destroy too:
# its actions are ["delete", "create"], or ["create", "delete"] under create_before_destroy.
# "forget" (a removed block with destroy = false) leaves the object in place and is allowed.
deny contains msg if {
	some p in plans
	not may_destroy(p.path)
	some rc in p.plan.resource_changes
	"delete" in rc.change.actions
	msg := sprintf(
		"%s: the plan destroys %s (actions %v); only a stack under infra/burst/ may destroy",
		[where(p.path), rc.address, rc.change.actions],
	)
}

plans contains {"path": doc.path, "plan": doc.contents} if {
	is_array(input)
	some doc in input
}

plans contains {"path": "", "plan": input} if is_object(input)

may_destroy(path) if startswith(path, "infra/burst/")

where(path) := path if path != ""

where("") := "plan with no path"
