# Last Days Revival

This working tree preserves the history and attribution of the community
`LAST_DAYS` resource pack while modernizing it for current Minecraft Java
releases.

## Current target

- Minecraft Java: `26.2`
- Resource-pack format: `88.0`
- Baseline: `Gwolfski/LAST_DAYS`, branch `1.20.x`, commit
  `0f4f0ca632de13ede6cce115b1278b378d43ee5d`
- License: Creative Commons Attribution-NonCommercial-ShareAlike 4.0

## Repeat the audit

The audit compares this pack with Mojang's official client JAR:

```powershell
python tools\audit_resource_pack.py `
  --pack-root . `
  --client-jar .cache\26.2-client.jar `
  --minecraft-version 26.2 `
  --report-dir reports\26.2
```

Generated reports are written to `reports/26.2`. The texture backlog is
`missing_textures.csv`; known structural migrations are listed in
`legacy_migrations.csv`.

The Mojang client JAR is reference material only and must not be shipped with
the resource pack.
