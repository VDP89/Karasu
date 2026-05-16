# Karasu deploy runbook

> Bring-up source of truth for the UI-13 deployed operator
> surface. Covers TLS termination at a reverse proxy
> (caddy / nginx), credentials bootstrap, trusted-proxy
> threat model, common troubleshooting.

## Preamble

Karasu's HTTP surface is a stdlib `ThreadingHTTPServer`. It
does NOT terminate TLS itself — the brief §11 anticipated
`--tls-cert` / `--tls-key` flags are intentionally deferred:
the sealed UI-13 production shape is a reverse proxy
terminating TLS in front of a loopback-bound listener
(caddy / nginx → 127.0.0.1:8787). Direct-TLS is not on the
chunk-9 PR; reopens for UI-14+ if dogfood demands it.

The deployed posture puts a reverse proxy in front (caddy
or nginx) that:

  1. Owns the public IP + DNS + cert.
  2. Terminates TLS.
  3. Forwards the request to `karasu ui` on a loopback
     port (the `--host 127.0.0.1` default).

Auth is the default at `karasu ui` startup. The
`--no-auth` flag exists for localhost iteration ONLY; the
startup refuses to combine it with a non-loopback bind or
with an explicit `auth.trusted_proxies` in `karasu.yaml`.

## 1. Bring-up from scratch

### 1.1 Bootstrap the credentials store

```sh
karasu auth set-credentials --username victor
# Password: ******** (no echo)
# Confirm:  ********
# karasu auth credentials written to .karasu/karasu-auth.json
#   -> mode 0600 on POSIX (advisory on Windows; verify NTFS ACLs).
```

The credentials file lands next to the configured bus log
(default `.karasu/karasu-auth.json`, gitignored). To
override:

```sh
karasu auth set-credentials \
  --credentials /etc/karasu/karasu-auth.json \
  --username victor
```

For ops automation (CI / installer scripts) without a TTY,
pipe the password on stdin:

```sh
printf '%s' "$PASSWORD" | karasu auth set-credentials \
  --username victor \
  --credentials /etc/karasu/karasu-auth.json
```

### 1.2 Configure trusted proxies

`karasu.yaml`:

```yaml
auth:
  trusted_proxies:
    - 127.0.0.1            # caddy / nginx on the same box
    - ::1
  expected_origins:
    - https://karasu.example.com
```

The defaults if `auth:` is absent are
`trusted_proxies: ["127.0.0.1", "::1"]` and
`expected_origins: []`. The deployed posture MUST set
`expected_origins` to the public origin so cross-site
mutating requests hit the §3-F 403 branch.

### 1.3 Caddy reverse proxy

Caddy's default behaviour overwrites `X-Forwarded-For`
correctly. The §3-G binding directive is explicit:

```caddy
karasu.example.com {
  reverse_proxy 127.0.0.1:8787 {
    header_up X-Forwarded-For {client_ip}
    header_up X-Forwarded-Proto {scheme}
    header_up Host {host}
  }
}
```

`{client_ip}` is the immediate peer that connected to
caddy. The right-to-left walk in the app +
`auth.trusted_proxies: [127.0.0.1]` resolves the real
client even if a malicious `X-Forwarded-For` header is
supplied upstream.

### 1.4 Nginx reverse proxy

Nginx's idiomatic `$proxy_add_x_forwarded_for` APPENDS the
peer to the client-supplied chain — that combined with a
leftmost-wins parse on the app side opens the bypass that
§3-G round 2 P1 closed. The runbook pins the OVERWRITE
form:

```nginx
server {
  listen 443 ssl http2;
  server_name karasu.example.com;
  ssl_certificate     /etc/ssl/karasu/fullchain.pem;
  ssl_certificate_key /etc/ssl/karasu/privkey.pem;

  location / {
    proxy_pass         http://127.0.0.1:8787;

    # OVERWRITE — never $proxy_add_x_forwarded_for (§3-G).
    proxy_set_header   X-Forwarded-For   $remote_addr;
    proxy_set_header   Forwarded         "for=$remote_addr;proto=$scheme";

    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_redirect     off;
  }
}
```

### 1.5 Start the listener

```sh
karasu ui --host 127.0.0.1 --port 8787
```

The startup checks (§3-B fail-closed):

  * `karasu-auth.json` present, mode 0600 on POSIX,
    JSON-parseable, scrypt parameters match
    `(N=16384, r=8, p=1)`, salt 16 B, hash 32 B,
    signing secret ≥ 32 B, `credentials_generation` ≥ 0.
  * `auth.trusted_proxies` non-empty when `--host` is
    non-loopback.

Any failure → exit 2 + generic stderr (`error: karasu
auth credentials are missing or malformed; refusing to
start. See docs/deploy-runbook.md for bring-up.`). NO
secret material in the message; NO file path.

### 1.6 Provision VAPID push keys (`karasu watch` bootstrap)

The UI-12c push pipeline needs an ECDSA P-256 VAPID
keypair before any browser can subscribe to push. The
keypair lives in `karasu-push.json` next to the bus log;
`karasu watch` auto-generates it on first start when the
file has no `vapid` section. **`karasu ui` does NOT
provision VAPID** — the UI process only reads the push
store. An operator who runs `karasu ui` alone will see
the UI-12b push modal flag *"VAPID keys not
provisioned"* on every opt-in attempt.

Bring-up:

```sh
# First-time provisioning. Generates the keypair under
# the UI-12c §3-G cross-process file lock, then begins
# watching. Stop and restart safely — subsequent starts
# read the existing pair and skip generation.
karasu watch
```

Run `karasu watch` under the same service supervisor as
`karasu ui` (systemd, launchd, NSSM on Windows) so both
processes are healthy in deployed posture. The two share
the same bus log + push store under the cross-process
file lock; concurrent reads + writes are safe.

Production: set the VAPID JWT `mailto:` claim in
`karasu.yaml` to a real contact (the default
`operator@localhost.invalid` is fine for dev but some
push services warn or rate-limit on the invalid TLD in
deployed posture):

```yaml
push:
  contact_email: ops@example.com
```

Rotation is operator-driven (delete `karasu-push.json`,
restart `karasu watch`); the emitter never rotates
automatically because doing so invalidates every
existing browser subscription atomically (UI-12 §10.4
binding). If a rotation is required (e.g. suspected
keypair leak), warn subscribed operators first — every
PWA install will need to re-subscribe via the footer
modal after the new keypair is bootstrapped.

The push store file follows the same posture as
`karasu-auth.json`: mode 0600 on POSIX (advisory on
Windows), NTFS ACLs restricting it to the karasu service
account in deployed Windows posture (see §6).

## 2. mkcert dev flow

For local TLS testing without a public cert:

```sh
mkcert -install
mkcert -cert-file karasu-dev.pem -key-file karasu-dev-key.pem \
  karasu.localhost 127.0.0.1 ::1
```

Front the local `karasu ui` with caddy bound to the
mkcert pair:

```caddy
karasu.localhost {
  tls karasu-dev.pem karasu-dev-key.pem
  reverse_proxy 127.0.0.1:8787 {
    header_up X-Forwarded-For {client_ip}
  }
}
```

Browser hits `https://karasu.localhost`; caddy terminates
TLS; the listener stays on plain HTTP / loopback. The
deployed-posture cookies (Secure flag) work because caddy
is the TLS endpoint and the app reads the
`X-Forwarded-Proto: https` header.

## 3. Credential rotation

```sh
karasu auth set-credentials --username victor
# → bumps credentials_generation by 1
# → rotates session_signing_secret by default
# → atomically replaces karasu-auth.json
```

Effect:

  * Every existing session cookie carries the OLD `gen`;
    middleware compares against the new `gen` and rejects.
    All sessions invalidated atomically.
  * Every existing CSRF cookie is bound to the OLD signing
    secret; verification fails on the next mutating
    request. The page-side fetch wrapper detects the
    resulting 401 / redirect-to-/ and POSTs
    `auth:revoked` to the SW so the post-auth cache is
    cleared.

The ops side does NOT need to restart `karasu ui` —
`load_credentials` is called per request (cached in the
process; the live process picks up the new file on the
next request via the chunk-7 startup wiring + the
auth-failure revocation flow). For a hard cut, restart
the process.

## 4. Trusted-proxy threat model

The trusted-proxy list is the boundary between
`peer_addr` and the right-to-left chain walk:

  * Peer IS in `trusted_proxies` → walk the chain right-
    to-left, return first non-trusted IP.
  * Peer NOT in `trusted_proxies` AND a forwarding chain
    is supplied → the peer is forging proxy intent;
    refuse the chain entirely (sentinel
    `UNTRUSTED_FORWARDED`). NO loopback bypass; fresh
    rate-limit slot keyed by the peer addr (server-layer
    fix re-keys to `!untrusted:<peer>` so the slot key
    can never match `is_loopback_ip`).
  * Peer NOT in `trusted_proxies` AND NO chain → genuine
    direct connect (e.g. `--no-auth` localhost dev
    posture).

Threats:

  * **Operator wipes `auth.trusted_proxies` to `[]`** —
    deployed-posture startup refuses to bind (§3-G
    Codex round 3 P1).
  * **Operator uses nginx `$proxy_add_x_forwarded_for`**
    — leftmost entry of the chain is attacker-supplied,
    but the right-to-left walk skips it; attacker IP
    surfaces from the proxy-appended position.
  * **Attacker supplies `X-Forwarded-For: 127.0.0.1` to
    a public listener** — peer is the attacker (NOT in
    `trusted_proxies`), so derive returns
    `UNTRUSTED_FORWARDED`; rate-limit slot keys by peer,
    no bypass.
  * **Proxy host compromise** — full bypass. The
    deployed posture trusts the proxy box's word about
    the peer IP; an attacker controlling the proxy can
    spoof anything. Mitigations belong at the proxy
    layer (audit, isolation, restricted access).

## 5. Troubleshooting

### Cookies do not stick (Set-Cookie ignored)

The deployed posture sets `Secure` on both cookies. If
the browser receives them over HTTP (proxy misconfigured,
direct hit on `:8787`), they will not stick. Check:

```sh
curl -i https://karasu.example.com/auth/login \
  -H "Origin: https://karasu.example.com" \
  -H "Content-Type: application/json" \
  -d '{"username":"victor","password":"hunter2"}' \
  | grep -i set-cookie
```

The `Set-Cookie` lines must include `Secure`, `Path=/`,
`SameSite=Strict`, and the session line `HttpOnly`.

### Login returns 403 even with the right password

Origin / Referer mismatch in deployed posture. Verify:

  * `auth.expected_origins` in `karasu.yaml` includes the
    exact public origin (scheme + host + port if
    non-default).
  * The proxy forwards the `Origin` header verbatim
    (caddy default). Nginx requires
    `proxy_set_header Origin $http_origin;` if you've
    custom-stripped headers.

### Login returns 429 immediately

The per-IP or per-credentials bucket tripped during a
prior burst. Buckets are restart-cleared by design.
Either:

  * Wait out the backoff (60 s initial, doubling cap
    1 hour).
  * Restart `karasu ui` (clears the in-memory rate-limit
    state).

If 429 is repeatedly tripped without a real burst, check
that `_ip_for_rate_limit` is keying off the real client
(the proxy is forwarding XFF correctly + `trusted_proxies`
includes the proxy IP).

### Page redirects to `/` from `/api/*` calls in a loop

The browser's session cookie expired or the
`credentials_generation` was bumped on disk. The page-
side fetch wrapper detected a 401 / redirect-to-/ and
posted `auth:revoked` to the SW. Reload — `/` now
renders the login surface. After re-login the post-auth
cache repopulates on `auth:granted`.

### TLS cert expired / mkcert root absent

Browser shows a security warning. Check:

  * `mkcert -install` was run on this machine.
  * The cert files referenced in caddy/nginx exist + are
    readable by the proxy user.
  * The cert covers the hostname the browser is hitting.

### Fail-closed startup messages

```text
error: karasu auth credentials are missing or malformed;
       refusing to start. See docs/deploy-runbook.md for
       bring-up.
```

→ Run `karasu auth set-credentials` (or restore the file
   to mode 0600 + valid JSON shape).

```text
error: --no-auth requires --host on a loopback address
       (127.0.0.1, ::1, or localhost); refusing to start.
```

→ Drop `--no-auth` for the deployed posture, or set
   `--host 127.0.0.1`.

```text
error: --no-auth incompatible with auth.trusted_proxies
       in karasu.yaml (signals deployed intent); refusing
       to start.
```

→ Either remove `auth.trusted_proxies` from
   `karasu.yaml` (dev posture) OR drop `--no-auth`
   (deployed posture).

```text
error: deployed posture requires non-empty
       auth.trusted_proxies; refusing to start. See
       docs/deploy-runbook.md for the trusted-hop walk
       requirements.
```

→ Set `auth.trusted_proxies: ["127.0.0.1", "::1"]` or
   the operator's deployed proxy IPs.

## 6. Windows posture

The `karasu-auth.json` mode-0600 enforcement is advisory
on Windows (POSIX file modes do not map cleanly). The
listener emits a stderr warning on startup:

```text
WARNING karasu.ui.auth: Windows posture detected; file
mode enforcement is advisory only. Verify NTFS ACLs
restrict the credentials file to the karasu service
account. See docs/deploy-runbook.md.
```

Apply NTFS ACLs manually:

```powershell
icacls .karasu\karasu-auth.json /inheritance:r
icacls .karasu\karasu-auth.json /grant:r "karasu-svc:(R,W)"
icacls .karasu\karasu-auth.json /remove "Users"
```

Replace `karasu-svc` with the account running
`karasu ui` on the host.
