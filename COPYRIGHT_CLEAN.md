# Copyright-clean packaging

This package does not redistribute original or derived 3D Pinball - Space Cadet game assets.

The user provides their own original installation locally. The guided builder then creates on the user's computer:

- `PINBALL.DAT`, copied from the user's own installation for runtime use;
- `SFXBANK.BIN`, generated from the user's original `SOUND*.WAV` files;
- `PINBALL.WAV`, generated from the user's original `PINBALL.MID`;
- `EBOOT.PBP`, built from the open-source project plus the PSP port patches.

The clean package itself does not contain `PINBALL.DAT`, `SFXBANK.BIN`, `PINBALL.WAV`, `SOUND*.WAV`, or a SoundFont.

If no local SoundFont is found, the builder downloads GeneralUser GS into the user's cache and verifies a pinned SHA-256 before use. The SoundFont is not added to the package or output folder.

## Deterministic music loop

The builder does not trim music based on silence thresholds. It verifies the known structure of the original `PINBALL.MID`: nine identical musical blocks starting at tick 1920, each 53760 ticks long. It renders three verified copies and extracts the middle copy using MIDI-derived timing (about 58.434768 seconds / 1,288,487 samples at 22050 Hz). If the expected MIDI structure is not present, the build fails instead of guessing.

This packaging approach is intended to avoid redistributing copyrighted game data, but it is not legal advice and cannot guarantee compliance in every jurisdiction.
