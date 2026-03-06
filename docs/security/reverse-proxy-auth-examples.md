# Reverse Proxy Auth Examples

These examples assume dashboard is local: `http://127.0.0.1:5001`.

## Caddy with forward auth
```caddyfile
agentplan.example.com {
  reverse_proxy 127.0.0.1:5001

  @protected {
    path *
  }
  forward_auth auth.example.com {
    uri /verify
    copy_headers X-User X-Email
  }

  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    X-Frame-Options "DENY"
    X-Content-Type-Options "nosniff"
    Referrer-Policy "no-referrer"
  }
}
```

## Nginx with auth_request
```nginx
server {
  listen 443 ssl http2;
  server_name agentplan.example.com;

  location = /_auth {
    internal;
    proxy_pass http://auth-gateway/verify;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Original-URI $request_uri;
  }

  location / {
    auth_request /_auth;
    proxy_pass http://127.0.0.1:5001;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
  }
}
```

## Cloudflare Access + tunnel
```yaml
ingress:
  - hostname: agentplan.example.com
    service: http://127.0.0.1:5001
  - service: http_status:404
```

Cloudflare Access policy suggestion:
- require identity provider login
- restrict by approved email domain/group
- enforce session duration <= 12h
