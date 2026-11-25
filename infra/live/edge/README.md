# infra/live/edge

The Cloudflare zone: DNS, the WAF flood rule and the Tunnel; later Access, Turnstile and Email
Routing (master plan §9).

Empty for now: only the OpenTofu version is pinned. The zone, DNS and the WAF rule need a domain,
and none is bought for now (design note §12.1). The Tunnel belongs to the account rather than
the zone, but whether one can be created on an account with no zone is a setup check (§12.1),
and cloudflared first needs it on the paid node (task 7), so it is written then.
`mise run tofu:plan` plans it read-only; applies run from CI, never from a session.
