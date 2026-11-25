#!/bin/sh
# Checks one saved plan against infra/policy/plan.rego: nothing outside infra/burst/ may destroy.
# The plan comes on stdin, as `tofu show -json` prints it; the argument is the stack's folder,
# relative to the repository root, which is how the policy knows where the plan comes from.
# `mise run tofu:plan` runs it for every stack, and policy/tests runs it on the fixtures.
#
#   tofu -chdir=infra/live/storage show -json <plan> | sh infra/policy/check-plan.sh infra/live/storage
set -eu

if [ $# -ne 1 ]; then
  echo "usage: tofu show -json <plan> | sh infra/policy/check-plan.sh <stack folder>" >&2
  exit 2
fi

exec conftest test --no-color --combine --parser json \
  --policy "$(dirname "$0")" --namespace globalens.plan \
  --stdin-filename "${1%/}/tfplan.json" -
