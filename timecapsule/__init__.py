"""Time Capsule -- a manifest-based launcher for legacy DOS/Windows software.

The capsule does **not** embed any emulator. It reads ``manifest.json`` (the
*app index*) and hands each entry to the emulator that suits it: Wine for
Windows games/apps that can use the host GPU, DOSBox-X for DOS titles. Keeping
the emulators external means the capsule can use real 3D acceleration instead
of a 2D-only virtual adapter.

Only the Python standard library is used, so the repository stays portable.
"""

__all__ = ["manifest", "emulators"]
__version__ = "1.0.0"
