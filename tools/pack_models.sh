#!/bin/sh
# Compress the Blender-exported GLBs in place with meshopt (geometry only;
# textures are already JPEG/PNG). Skips files that are already packed.
# Run after any tools/blender/build_*.py:  sh tools/pack_models.sh
cd "$(dirname "$0")/.." || exit 1
for f in public/assets/models/*.glb; do
  if grep -q "EXT_meshopt_compression" "$f"; then echo "packed: $f"; continue; fi
  npx gltfpack -i "$f" -o "$f.tmp.glb" -cc -kn -km -ke && mv "$f.tmp.glb" "$f" && echo "packed $f"
done
