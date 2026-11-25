# infra/live/storage

The R2 buckets of Phase 1, their lifecycle rules, and the `cdn` bucket's public `r2.dev`
address (design note §6, §12.1). Everything carries `prevent_destroy`, and `infra/policy`
refuses a change that removes it, and any plan that destroys something. Applied from CI (task
16), never from a session; nothing has been applied yet. The state is
`storage/terraform.tfstate` in the bucket `infra/live/bootstrap` creates.

| Bucket | Holds | Lifecycle | Public |
|---|---|---|---|
| `globalens-raw` | GDELT's verified zips | deleted 7 days after they are written | no |
| `globalens-lake` | `facts/`, kept forever; `display/` (titles and URLs), kept and redactable | none | no |
| `globalens-cdn` | the data plane | `live/` deleted 48 hours after it is written; the rest kept | yes, through its `r2.dev` address |
| `globalens-fixtures` | the real fixture week and the frozen evaluation dumps | none | no |

Every bucket also aborts a multipart upload 7 days after it starts. That is R2's default rule,
restated because any lifecycle configuration replaces it. R2 removes an expired object within
about 24 hours of its expiry, so `raw` can hold 8 days of zips: about 9.6 GB at the design
note's 1.2 GB a day.

- **Names.** The first segment of a path in the design note is the bucket: `cdn/now.json` is the
  key `now.json` in `globalens-cdn`. The R2 client (the deploy tasks) maps `raw`, `lake`, `cdn`
  and `fixtures` to these names, which the output `buckets` lists.
- **The 48-hour rule on `live/`** rests on two properties of task 11's publisher: its window is
  the 24 closed hours plus the open hour (`WINDOW` in `apps/worker/src/worker/dataplane.py`), and
  it never rewrites a key that exists (it asks with a HEAD first). So nothing refers to an object
  under `live/` more than about 25 hours after it is written. If the window grows past about
  46 hours, the rule must grow with it.
- **The `r2.dev` address** is switched on by `cloudflare_r2_managed_domain`, a resource of the
  pinned provider (5.29.0). That answers the setup question in §12.1, whether the provider can do
  it; the first apply confirms that the resource works. If it does not, the address is switched
  on once by hand (the bucket's Settings, "Public Development URL") and that is recorded here.
  Its host (`pub-….r2.dev`) is the output `cdn_r2_dev_domain`, for task 12's Content Security
  Policy and task 16's deploy. Cloudflare rate-limits the address and does not cache it at the
  edge.
- **Waits for its task:** the CORS rule on `cdn` (task 16, once the site has its `workers.dev`
  origin), the bucket lock on `lake/facts/` (task 20, at the Phase 1 close: Q17), and the buckets
  of later phases (`exports` and `models` in P2, `snap` in P4).
- **Waits for a domain** (§12.1): the `cdn` custom domain and its Cache Rules.
- **Tokens.** Applying needs an account API token with "Workers R2 Storage: Edit"; planning
  needs "Workers R2 Storage: Read". The per-bucket R2 tokens for the nodes and CI (master plan
  §9) arrive with the deploy tasks.
- **Standard storage only.** R2's free allowance covers Standard storage, so `infra/policy`
  refuses Infrequent Access, which would be a recurring cost.
