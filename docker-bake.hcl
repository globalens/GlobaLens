# Every image of the GlobaLens nodes, each for linux/amd64 and linux/arm64: the paid node is
# x86-64 and the free node arm64, and nothing may assume one of them (CLAUDE.md). Run from the
# repository root; why these images: docs/adr/0013-node-images.md.
#
#   mise run images                        both architectures of every image (no push)
#   docker buildx bake --load --set '*.platform=linux/arm64'    this Mac's, into Docker
#
# Task 16's workflow builds the same targets on GitHub's x64 and arm64 runners and pushes them to
# GHCR; prod.lock then names their digests. Nothing here pushes.

variable "TAG" {
  default = "local"
}

group "default" {
  targets = ["postgres", "migrate", "worker", "edge"]
}

target "_both" {
  platforms = ["linux/amd64", "linux/arm64"]
}

target "postgres" {
  inherits   = ["_both"]
  context    = "db"
  dockerfile = "Dockerfile"
  target     = "server"
  tags       = ["globalens/postgres:${TAG}"]
}

target "migrate" {
  inherits   = ["_both"]
  context    = "db"
  dockerfile = "Dockerfile"
  target     = "migrate"
  tags       = ["globalens/migrate:${TAG}"]
}

target "worker" {
  inherits   = ["_both"]
  context    = "."
  dockerfile = "apps/worker/Dockerfile"
  target     = "worker"
  tags       = ["globalens/worker:${TAG}"]
}

target "edge" {
  inherits   = ["_both"]
  context    = "."
  dockerfile = "apps/worker/Dockerfile"
  target     = "edge"
  tags       = ["globalens/edge:${TAG}"]
}
