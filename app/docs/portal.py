"""Docs portal: overview landing page and Scalar API reference."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from scalar_fastapi import (
    AgentScalarConfig,
    DocumentDownloadType,
    Layout,
    SearchHotKey,
    get_scalar_api_reference,
)

from app.docs.openapi import API_VERSION, OPENKEY_SCALAR_CSS

router = APIRouter(include_in_schema=False)

_DOCS_OVERVIEW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="OpenKey zero-knowledge sync API — operator and client integration guide." />
  <title>OpenKey Sync API</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --ok-ink: #10241c;
      --ok-ink-soft: #4a6358;
      --ok-paper: #f3f6f4;
      --ok-paper-deep: #e6ece8;
      --ok-teal: #0f5c4c;
      --ok-teal-bright: #187a64;
      --ok-mint: #5eb89a;
      --ok-line: rgba(16, 36, 28, 0.1);
      --ok-display: 'Bricolage Grotesque', Georgia, serif;
      --ok-body: 'Source Sans 3', system-ui, sans-serif;
      --ok-mono: 'IBM Plex Mono', ui-monospace, monospace;
      --ok-shadow: 0 18px 48px rgba(16, 36, 28, 0.08);
      --ok-radius: 16px;
    }

    * { box-sizing: border-box; }

    html, body {
      margin: 0;
      min-height: 100%;
      background:
        radial-gradient(1100px 520px at 12% -8%, rgba(15, 92, 76, 0.09), transparent 58%),
        radial-gradient(900px 480px at 100% 0%, rgba(94, 184, 154, 0.08), transparent 52%),
        var(--ok-paper);
      color: var(--ok-ink);
      font-family: var(--ok-body);
      line-height: 1.55;
    }

    a { color: var(--ok-teal); text-decoration: none; }
    a:hover { color: var(--ok-teal-bright); }

    .shell { max-width: 1120px; margin: 0 auto; padding: 0 24px 72px; }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 20px 0 28px;
      border-bottom: 1px solid var(--ok-line);
      margin-bottom: 40px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-family: var(--ok-display);
      font-weight: 700;
      font-size: 1.15rem;
      color: var(--ok-ink);
    }

    .brand svg { flex-shrink: 0; }

    .nav {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 10px 16px;
      border-radius: 999px;
      font-weight: 600;
      font-size: 0.95rem;
      border: 1px solid transparent;
      transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
    }

    .btn-primary {
      background: var(--ok-teal);
      color: #f4faf7;
    }

    .btn-primary:hover {
      background: var(--ok-teal-bright);
      color: #f4faf7;
    }

    .btn-ghost {
      background: rgba(255, 255, 255, 0.55);
      border-color: var(--ok-line);
      color: var(--ok-ink);
    }

    .btn-ghost:hover {
      background: #fff;
      border-color: rgba(15, 92, 76, 0.22);
    }

    .hero {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 28px;
      align-items: stretch;
      margin-bottom: 36px;
    }

    .hero-copy {
      padding: 8px 0;
    }

    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      border-radius: 999px;
      background: rgba(15, 92, 76, 0.08);
      color: var(--ok-teal);
      font-size: 0.82rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      margin-bottom: 18px;
    }

    h1 {
      font-family: var(--ok-display);
      font-size: clamp(2rem, 4vw, 3rem);
      line-height: 1.08;
      margin: 0 0 16px;
      letter-spacing: -0.02em;
    }

    .lead {
      font-size: 1.08rem;
      color: var(--ok-ink-soft);
      max-width: 58ch;
      margin: 0 0 24px;
    }

    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 18px;
    }

    .meta-row {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      color: var(--ok-ink-soft);
      font-size: 0.92rem;
    }

    .meta-row code {
      font-family: var(--ok-mono);
      font-size: 0.86rem;
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid var(--ok-line);
      border-radius: 8px;
      padding: 2px 8px;
      color: var(--ok-ink);
    }

    .hero-card {
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid var(--ok-line);
      border-radius: var(--ok-radius);
      box-shadow: var(--ok-shadow);
      padding: 22px;
      backdrop-filter: blur(8px);
    }

    .hero-card h2 {
      margin: 0 0 14px;
      font-size: 1rem;
      font-weight: 700;
    }

    .flow {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 12px;
    }

    .flow li {
      display: grid;
      grid-template-columns: 28px 1fr;
      gap: 12px;
      align-items: start;
    }

    .step-num {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: rgba(15, 92, 76, 0.12);
      color: var(--ok-teal);
      font-size: 0.82rem;
      font-weight: 700;
    }

    .flow strong { display: block; margin-bottom: 2px; }
    .flow span { color: var(--ok-ink-soft); font-size: 0.92rem; }

    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
      margin-bottom: 28px;
    }

    .card {
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid var(--ok-line);
      border-radius: var(--ok-radius);
      padding: 20px;
      min-height: 100%;
    }

    .card h3 {
      margin: 0 0 10px;
      font-size: 1rem;
    }

    .card p {
      margin: 0;
      color: var(--ok-ink-soft);
      font-size: 0.95rem;
    }

    .section {
      margin-bottom: 28px;
    }

    .section h2 {
      font-family: var(--ok-display);
      font-size: 1.45rem;
      margin: 0 0 14px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid var(--ok-line);
      border-radius: var(--ok-radius);
      overflow: hidden;
    }

    th, td {
      text-align: left;
      padding: 12px 14px;
      border-bottom: 1px solid var(--ok-line);
      vertical-align: top;
      font-size: 0.94rem;
    }

    th {
      background: rgba(15, 92, 76, 0.06);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--ok-ink-soft);
    }

    tr:last-child td { border-bottom: 0; }

    td code {
      font-family: var(--ok-mono);
      font-size: 0.84rem;
      background: rgba(15, 92, 76, 0.06);
      border-radius: 6px;
      padding: 2px 6px;
    }

    .method {
      display: inline-block;
      min-width: 58px;
      font-family: var(--ok-mono);
      font-size: 0.78rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }

    .method-get { color: #0f5c4c; }
    .method-post { color: #187a64; }
    .method-patch { color: #8a5a12; }
    .method-delete { color: #9b2c2c; }

    .callout {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 14px;
      align-items: start;
      padding: 18px 20px;
      border-radius: var(--ok-radius);
      border: 1px solid rgba(15, 92, 76, 0.18);
      background: linear-gradient(135deg, rgba(15, 92, 76, 0.08), rgba(94, 184, 154, 0.08));
      margin-bottom: 28px;
    }

    .callout strong { display: block; margin-bottom: 4px; }
    .callout p { margin: 0; color: var(--ok-ink-soft); }

    .footer {
      margin-top: 36px;
      padding-top: 22px;
      border-top: 1px solid var(--ok-line);
      color: var(--ok-ink-soft);
      font-size: 0.92rem;
      display: flex;
      flex-wrap: wrap;
      gap: 12px 18px;
      justify-content: space-between;
    }

    @media (max-width: 900px) {
      .hero, .grid { grid-template-columns: 1fr; }
      .topbar { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand" aria-label="OpenKey">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="2" y="2" width="20" height="20" rx="6" fill="#0f5c4c"/>
          <path d="M8.5 11.5c0-1.93 1.57-3.5 3.5-3.5s3.5 1.57 3.5 3.5v1.2c1.1.35 1.9 1.4 1.9 2.6v2.1c0 1.55-1.26 2.8-2.8 2.8h-5.2c-1.54 0-2.8-1.25-2.8-2.8v-2.1c0-1.2.8-2.25 1.9-2.6v-1.2z" fill="#f3f6f4"/>
          <circle cx="12" cy="11.5" r="1.1" fill="#0f5c4c"/>
        </svg>
        <span>OpenKey Sync API</span>
      </div>
      <nav class="nav" aria-label="Documentation">
        <a class="btn btn-ghost" href="/docs/reference">API reference</a>
        <a class="btn btn-ghost" href="/openapi.json">OpenAPI</a>
        <a class="btn btn-ghost" href="/health">Health</a>
        <a class="btn btn-primary" href="/docs/reference">Explore endpoints</a>
      </nav>
    </header>

    <section class="hero">
      <div class="hero-copy">
        <div class="eyebrow">Zero-knowledge · Self-hosted</div>
        <h1>Sync vault ciphertext across your devices</h1>
        <p class="lead">
          OpenKey Server is the optional sync backend for OpenKey clients. It stores encrypted blobs,
          wrapped keys, and authentication material — never master passwords or decrypted vault data.
        </p>
        <div class="hero-actions">
          <a class="btn btn-primary" href="/docs/reference">Open interactive reference</a>
          <a class="btn btn-ghost" href="https://openkey.dev/guide/server" rel="noopener">Deployment guide</a>
        </div>
        <div class="meta-row">
          <span>Version <code>__API_VERSION__</code></span>
          <span>Spec <code>/openapi.json</code></span>
          <span>Auth <code>Bearer JWT</code></span>
        </div>
      </div>

      <aside class="hero-card" aria-labelledby="auth-flow-title">
        <h2 id="auth-flow-title">Client authentication flow</h2>
        <ol class="flow">
          <li>
            <span class="step-num">1</span>
            <div>
              <strong>Prelogin</strong>
              <span><code>POST /auth/prelogin</code> returns salt and KDF parameters for the email.</span>
            </div>
          </li>
          <li>
            <span class="step-num">2</span>
            <div>
              <strong>Derive locally</strong>
              <span>The client derives <code>auth_hash</code> and vault keys from the master password.</span>
            </div>
          </li>
          <li>
            <span class="step-num">3</span>
            <div>
              <strong>Login or register</strong>
              <span><code>POST /auth/login</code> or <code>/auth/register</code> returns access + refresh tokens.</span>
            </div>
          </li>
          <li>
            <span class="step-num">4</span>
            <div>
              <strong>Sync ciphertext</strong>
              <span>Send <code>Authorization: Bearer …</code> on vault, org, share, and sync routes.</span>
            </div>
          </li>
        </ol>
      </aside>
    </section>

    <div class="callout" role="note">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2l8.5 4.9v9.8L12 22 3.5 16.7V6.9L12 2z" stroke="#0f5c4c" stroke-width="1.6"/>
        <path d="M12 8v5" stroke="#0f5c4c" stroke-width="1.6" stroke-linecap="round"/>
        <circle cx="12" cy="16.2" r="0.9" fill="#0f5c4c"/>
      </svg>
      <div>
        <strong>Security model</strong>
        <p>
          Collection names, entry payloads, attachments, organization names, and share data are opaque ciphertext.
          Refresh tokens rotate on every use; reuse of a rotated token revokes all sessions for that account.
          Auth endpoints are rate-limited per client IP.
        </p>
      </div>
    </div>

    <section class="grid" aria-label="API surface">
      <article class="card">
        <h3>Personal vault</h3>
        <p>Collections, entries, attachments, and batch <code>/sync</code> for last-write-wins replication across devices.</p>
      </article>
      <article class="card">
        <h3>Organizations</h3>
        <p>Shared org vaults with invites, roles, wrapped org keys, and org-scoped collections and entries.</p>
      </article>
      <article class="card">
        <h3>Direct shares</h3>
        <p>Share encrypted items or collections with other users on the same server using wrapped item keys.</p>
      </article>
    </section>

    <section class="section" aria-labelledby="endpoints-title">
      <h2 id="endpoints-title">Endpoint map</h2>
      <table>
        <thead>
          <tr>
            <th>Area</th>
            <th>Base path</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Auth &amp; sessions</td>
            <td><code>/auth/*</code></td>
            <td>Register, prelogin, login, refresh rotation, rekey, account delete.</td>
          </tr>
          <tr>
            <td>Personal vault</td>
            <td><code>/collections</code>, <code>/entries</code>, <code>/attachments</code></td>
            <td>Ciphertext CRUD; attachments support multipart upload up to 20 MB.</td>
          </tr>
          <tr>
            <td>Batch sync</td>
            <td><code>/sync</code></td>
            <td>Push local changes and pull updates since a microsecond cursor.</td>
          </tr>
          <tr>
            <td>Organizations</td>
            <td><code>/orgs/*</code>, <code>/invites/*</code></td>
            <td>Invites, membership, shared collections and entries.</td>
          </tr>
          <tr>
            <td>Shares</td>
            <td><code>/shares/*</code></td>
            <td>Pending → accepted / revoked; entry shares snapshot ciphertext.</td>
          </tr>
          <tr>
            <td>Operations</td>
            <td><code>/health</code></td>
            <td>Database readiness for monitoring and load balancers.</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="section" aria-labelledby="quickstart-title">
      <h2 id="quickstart-title">Quick start</h2>
      <table>
        <thead>
          <tr>
            <th>Step</th>
            <th>Request</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>1</td>
            <td><span class="method method-post">POST</span> <code>/auth/prelogin</code></td>
            <td>Salt and KDF parameters for client-side derivation.</td>
          </tr>
          <tr>
            <td>2</td>
            <td><span class="method method-post">POST</span> <code>/auth/login</code></td>
            <td>Access JWT, refresh token, and <code>expires_in</code>.</td>
          </tr>
          <tr>
            <td>3</td>
            <td><span class="method method-get">GET</span> <code>/auth/me</code></td>
            <td>Unlock bootstrap: wrapped vault key, salt, and KDF params.</td>
          </tr>
          <tr>
            <td>4</td>
            <td><span class="method method-post">POST</span> <code>/sync</code></td>
            <td>Push local ciphertext changes and pull server updates.</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="footer">
      <span>OpenKey Server · MIT License</span>
      <span>
        <a href="/docs/reference">API reference</a>
        ·
        <a href="/openapi.json">OpenAPI JSON</a>
        ·
        <a href="https://github.com/OpenSelfHosting" rel="noopener">GitHub</a>
      </span>
    </footer>
  </div>
</body>
</html>
""".replace("__API_VERSION__", API_VERSION)


@router.get("/docs", include_in_schema=False)
async def docs_overview() -> HTMLResponse:
    """Operator-facing overview and integration guide."""
    return HTMLResponse(content=_DOCS_OVERVIEW_HTML)


@router.get("/docs/", include_in_schema=False)
async def docs_overview_slash() -> RedirectResponse:
    return RedirectResponse(url="/docs", status_code=308)


@router.get("/redoc", include_in_schema=False)
async def legacy_redoc_redirect() -> RedirectResponse:
    return RedirectResponse(url="/docs/reference", status_code=308)


@router.get("/swagger", include_in_schema=False)
async def legacy_swagger_redirect() -> RedirectResponse:
    return RedirectResponse(url="/docs/reference", status_code=308)


@router.get("/docs/reference", include_in_schema=False)
async def docs_reference(request: Request) -> HTMLResponse:
    """Interactive OpenAPI reference powered by Scalar."""
    return get_scalar_api_reference(
        openapi_url=request.app.openapi_url or "/openapi.json",
        title="OpenKey Sync API",
        layout=Layout.MODERN,
        dark_mode=True,
        search_hot_key=SearchHotKey.K,
        document_download_type=DocumentDownloadType.BOTH,
        authentication={"preferredSecurityScheme": "BearerAuth"},
        persist_auth=True,
        custom_css=OPENKEY_SCALAR_CSS,
        agent=AgentScalarConfig(disabled=True),
        show_developer_tools="localhost",
        telemetry=False,
    )
