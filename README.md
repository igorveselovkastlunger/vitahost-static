# vitahost-static

Static mirror of vitahost.es (WordPress) for Vercel deployment.

## How it was built

```bash
python3 mirror.py
```

The script crawls `https://vitahost.es/sitemap.xml` plus the homepage, downloads every linked page and asset (CSS, JS, images, fonts), rewrites absolute `https://vitahost.es/` links to root-relative, and writes everything under `public/`.

## Layout

```
vitahost-static/
├── mirror.py           # crawler — re-run to refresh the snapshot
├── vercel.json         # Vercel config (cleanUrls + cache headers)
├── public/             # the deployable static site
│   ├── index.html
│   ├── pricing/index.html
│   ├── wp-content/uploads/...
│   └── ...
└── README.md
```

## Deploying

```bash
cd vitahost-static
npx vercel --prod
```

Once deployed, point `vitahost.es` at the new Vercel project.

## Forms

The original WordPress site used Contact Form 7. The static mirror replaces it with [Web3Forms](https://web3forms.com) — same fields, no backend required. See `public/contact-airbnb-property-management-torrevieja/index.html`.

## Refreshing the snapshot

Re-run `python3 mirror.py` from this directory. It deletes nothing — re-fetches all URLs from the sitemap. Commit the diff to re-deploy.
