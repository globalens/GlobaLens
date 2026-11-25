#!/bin/sh
# Rebuilds plan_mixed/plan.json and plan_destroy/plan.json: real `tofu show -json` output for
# every kind of change the plan policy has to tell apart. Run from infra/policy/testdata with
# OpenTofu on PATH (mise exec -- sh make-plans.sh). Nothing is applied and nothing leaves the
# machine: the only resources are terraform_data, which OpenTofu builds in, read from a state
# file written here by hand.
#
#   kept       in state and config, unchanged      -> ["no-op"]
#   added      in config only                      -> ["create"]
#   gone       in state only                       -> ["delete"]
#   replaced   triggers_replace changed            -> ["delete", "create"]
#   cbd        the same, create_before_destroy     -> ["create", "delete"]
#   forgotten  a removed block with destroy=false  -> ["forget"]
#
# plan_destroy is `tofu plan -destroy` of the same state: every resource -> ["delete"].
set -eu

here=$(pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

cat > "$work/main.tf" <<'EOF'
resource "terraform_data" "kept" {
  input = "a"
}

resource "terraform_data" "added" {
  input = "b"
}

resource "terraform_data" "replaced" {
  input            = "a"
  triggers_replace = "2"
}

resource "terraform_data" "cbd" {
  input            = "a"
  triggers_replace = "2"
  lifecycle {
    create_before_destroy = true
  }
}

removed {
  from = terraform_data.forgotten
  lifecycle {
    destroy = false
  }
}
EOF

instance() {
  # $1 id, $2 triggers_replace as JSON (null or a {"value", "type"} object)
  printf '{"schema_version": 0, "attributes": {"id": "%s", "input": {"value": "a", "type": "string"}, "output": {"value": "a", "type": "string"}, "triggers_replace": %s}, "sensitive_attributes": []}' "$1" "$2"
}

resource() {
  # $1 name, $2 triggers_replace as JSON
  printf '{"mode": "managed", "type": "terraform_data", "name": "%s", "provider": "provider[\\"terraform.io/builtin/terraform\\"]", "instances": [%s]}' "$1" "$(instance "id-$1" "$2")"
}

one='{"value": "1", "type": "string"}'
{
  printf '{"version": 4, "terraform_version": "1.13.9", "serial": 1, '
  printf '"lineage": "00000000-0000-4000-8000-000000000001", "outputs": {}, "resources": ['
  printf '%s, %s, %s, %s, %s' \
    "$(resource kept null)" "$(resource gone null)" "$(resource replaced "$one")" \
    "$(resource cbd "$one")" "$(resource forgotten null)"
  printf '], "check_results": null}\n'
} > "$work/terraform.tfstate"

tofu -chdir="$work" init -input=false -no-color > /dev/null
tofu -chdir="$work" plan -input=false -lock=false -refresh=false -no-color -out=mixed.tfplan > /dev/null
tofu -chdir="$work" plan -destroy -input=false -lock=false -refresh=false -no-color -out=destroy.tfplan > /dev/null

mkdir -p "$here/plan_mixed" "$here/plan_destroy"
tofu -chdir="$work" show -json mixed.tfplan | python3 -m json.tool --indent 2 > "$here/plan_mixed/plan.json"
tofu -chdir="$work" show -json destroy.tfplan | python3 -m json.tool --indent 2 > "$here/plan_destroy/plan.json"
echo "wrote plan_mixed/plan.json and plan_destroy/plan.json"
