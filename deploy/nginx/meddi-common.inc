# Shared by both MEDDI sites (see meddi.conf).

location ~ ^/(api|mock)/ {
    proxy_pass http://127.0.0.1:8100;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_buffering off;            # chat replies stream as server-sent events
    proxy_read_timeout 300s;
    client_max_body_size 20m;       # voice messages for transcription
}

# a new deploy must reach the browser at once: the page, the service worker and the manifest are never cached
location ~ ^/(index\.html|sw\.js|registerSW\.js|manifest\.webmanifest)$ {
    add_header Cache-Control "no-cache";
}

location /assets/ {
    add_header Cache-Control "public, max-age=31536000, immutable";
}

location / {
    try_files $uri $uri/ /index.html;
    add_header Cache-Control "no-cache";
}
