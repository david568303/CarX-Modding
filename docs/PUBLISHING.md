# Publishing CarX Drift Racing Online 2 releases

The native source is maintained in [UnityDoorstop](https://github.com/david568303/UnityDoorstop).
Push the signed Doorstop commit first, then pin it with a signed commit in
[CarX-Modding](https://github.com/david568303/CarX-Modding).
Keep private fixture inputs, caches and build output under ignored directories.

Build from a clean tagged checkout with the pinned submodule initialized.
See [the build instructions](SOURCE-BUILDS.md) and [tests](TESTING.md).

```powershell
$version = '2.0.0'
.\tools\build-release.ps1 -Version $version
```

The build creates an installable runtime ZIP, a separate complete source
ZIP with the Doorstop submodule included, and SHA-256 sidecars.
Both ZIPs include the licenses and notices. The runtime's
SOURCE-DOWNLOADS.txt lists the exact corresponding source revisions.

Upload both ZIPs and checksums on GitHub. Upload only the installable
runtime ZIP as the main file on Nexus. Use the same runtime ZIP on both
sites and verify the matching SHA-256. Check the new Nexus file's own
scan badge and download availability before retiring superseded files.
Keep quarantined files in the version history for staff review.

Older release entries can be retired while retaining their Git tags. The
tag and its pinned Doorstop submodule still provide the corresponding source.
