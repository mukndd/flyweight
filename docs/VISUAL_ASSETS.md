# Visual Assets

Last updated: 2026-09-14

## Current Runtime Assets

### Original procedural Drosophila runtime model

- Name: Flyweight Drosophila operator model
- Creator: Flyweight project
- Source: `apps/web/src/world3d.ts`
- License: project source license is not yet selected
- Modifications: original Three.js geometry; red compound eyes, golden abdomen/thorax, translucent wings, striped abdomen, six multi-segment legs, antennae, controller interaction animation
- Downloaded hash: not applicable; no external file downloaded
- Optimized hash: not applicable; runtime geometry only
- Attribution requirement: none beyond project authorship
- Rig state: lightweight transform hierarchy; no skeletal GLTF rig

### Original miniature controller runtime model

- Name: Flyweight compact controller
- Creator: Flyweight project
- Source: `apps/web/src/world3d.ts`
- License: project source license is not yet selected
- Modifications: original Three.js geometry; shell, stick, buttons, deterministic button/stick animation from Fly Brain actions
- Downloaded hash: not applicable; no external file downloaded
- Optimized hash: not applicable; runtime geometry only
- Attribution requirement: none beyond project authorship

### Original experimental combat mannequins

- Name: Flyweight combat mannequin pair
- Creator: Flyweight project
- Source: `apps/web/src/world3d.ts`
- License: project source license is not yet selected
- Modifications: original Three.js capsule/box geometry; warm Fly-controlled fighter, cool human/opponent fighter, action-state pose mapping
- Downloaded hash: not applicable; no external file downloaded
- Optimized hash: not applicable; runtime geometry only
- Attribution requirement: none beyond project authorship

### Original neural combat test chamber

- Name: Neural combat test chamber
- Creator: Flyweight project
- Source: `apps/web/src/world3d.ts`
- License: project source license is not yet selected
- Modifications: original Three.js geometry; graphite floor, grid markings, low rails, observation glass, overhead practical lighting
- Downloaded hash: not applicable; no external file downloaded
- Optimized hash: not applicable; runtime geometry only
- Attribution requirement: none beyond project authorship

## External Drosophila Model Investigation

No external model was downloaded in this pass.

The strongest apparent candidate found during web research was a Sketchfab listing titled "Drosophila - Adult Fruit Fly - CT Scan - Download Free 3D Model", described in search results as a Drosophila melanogaster adult CT-scan model published July 22, 2024. Sketchfab is not an allowed automated download source under the repository rule limiting network downloads to recognized official sources, and the visible search result did not provide enough license/provenance detail to ingest it safely. Manual review is required before use.

Suggested manual asset slot:

- Place reviewed source asset at: `apps/web/public/assets/drosophila/source/`
- Place optimized `.glb` derivative at: `apps/web/public/assets/drosophila/flyweight-drosophila.glb`
- Required before commit/use: source URL, creator, license, original byte size, SHA-256, optimized byte size, optimized SHA-256, triangle counts before/after, texture dimensions, attribution text if required

Other sources checked:

- MICRA Express Licensing has a "3D Printed Fruit fly" research-material listing, but the portal appears account/licensing oriented and was not used for automated download.
- FlyWire/Fly Connectome sources expose connectome and morphology concepts, not a lightweight, license-cleared whole-body Drosophila game asset suitable for immediate web runtime use.

## Connectome Spatial Visualization Status

External FlyWire spatial derivatives were investigated from Zenodo record `18555170`.

Downloaded for inspection:

- `coordinates.mat`
  - URL: `https://zenodo.org/api/records/18555170/files/coordinates.mat/content`
  - Downloaded: 2026-09-14
  - Bytes: 1,885,835
  - SHA-256: `12dffd790933c05210021683314a949aa2e9c4d69e81a0768be6decd6daa5aa2`
  - Upstream checksum: `md5:c55f622a86be58ea5c5b7c9fcb9ee24a`
  - Schema inspected: `coor`, shape `138639 x 3`, dtype `float64`
- `annotations.mat`
  - URL: `https://zenodo.org/api/records/18555170/files/annotations.mat/content`
  - Downloaded: 2026-09-14
  - Bytes: 574,256
  - SHA-256: `ebaa0f367b44edcdeb7297c8d6905226db19df102b4dc6b863154419b0a49ab9`
  - Upstream checksum: `md5:0d2be44229cd13bc2544e972397503ed`
  - Schema inspected: label/name category matrices; no root-ID vector found

The coordinate file confirms that real 3D cell-body coordinates exist externally, but the inspected coordinate/annotation pair does not provide an authoritative root-ID ordering. The current web protocol exposes a bounded sampled graph view: neuron IDs, roles, normalized edges, and live activity values. It does not expose verified per-neuron anatomical centroids, skeletons, meshes, neuropil labels, or safely joined FlyWire/Codex coordinates for the selected 1,536 runtime neurons.

Because the selected-neuron spatial metadata is not safely available in the client, the public visualization is intentionally labeled `CONNECTOME ACTIVITY MAP`, not anatomical brain. Runtime mapping is:

- sampled graph neuron index to deterministic display coordinate
- live recurrent activation magnitude to node brightness/size
- active connected pairs to highlighted paths
- input role to left sensory column
- readout role to right motor column
- internal role to central layered field

Limitations:

- Not anatomical.
- Not a real brain shell or neuropil rendering yet.
- Edges are a bounded display subset from the server graph view, not the full connectome.
- A future spatial map needs a verified root-ID-to-coordinate join before rendering.
