# Last Days Revival texture pipeline

Target: Minecraft Java 26.2, resource-pack format 88.0, 32 px base scale.

## Principles

1. Mojang's current texture is the semantic, size, alpha, and UV reference.
2. Existing Last Days textures are the palette and surface-language reference.
3. Closely related variants are derived from one approved material master.
4. Generated images remain candidates until 32 px reduction and visual QA pass.
5. Existing pack artwork is never overwritten by an automated builder.

## Asset classes

- **Path/layout migrations:** use Mojang Slicer or exact deterministic copying.
- **Material families:** generate or paint one base, then transfer official variant
  structure onto it.
- **Items and plants:** preserve the current Vanilla silhouette and alpha mask.
- **Entities/equipment:** preserve the current Vanilla UV map exactly.
- **GUI and particles:** process as separate coherent style families.

## Generation workflow

1. Put generated masters and prompts under `workbench/26.2/<family>/`.
2. Finalize a block master:

   ```powershell
   python tools/finalize_generated_block_texture.py `
     --input <master.png> `
     --vanilla-reference <official-reference.png> `
     --output <candidate.png> `
     --preview <preview.png>
   ```

3. Inspect the single-tile and 3x3 preview.
4. Install only after approval with `--apply-to <pack-asset.png>`.
5. Run the strict pack audit.

## Current deterministic builders

```powershell
python tools/build_shelf_family.py --apply
python tools/build_cinnabar_family.py --apply
```

Both builders use official Minecraft 26.2 layouts and install only missing
files. Their manifests and previews live under `workbench/26.2/`.

## Quality gates

- correct Minecraft path and dimensions
- valid PNG/JSON/metadata
- preserved alpha or UV layout
- no broken model references
- coherent Last Days palette and weathering
- no visible tile seams or dominant repetition bands
- no uncontrolled overwrite of original artwork

The source pack is licensed CC BY-NC-SA 4.0. Revival derivatives retain the
same attribution, non-commercial, and share-alike requirements.
